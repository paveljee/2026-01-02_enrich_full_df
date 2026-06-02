WITH base AS (
    SELECT
        "ktp.source_key",
        "ktp.fragment",
        try_cast("ktp.ssn_sum_hit_1pct" AS DOUBLE) AS ssn_sum_hit_1pct,
        try_cast("ssnad.works_count" AS DOUBLE) AS works_count,
        try_cast("ssnad.cited_by_count" AS DOUBLE) AS cited_by_count
    FROM card_partition_review
    WHERE try_cast("ktp.partition" AS INTEGER) = 2
),

bounds AS (
    SELECT
        "ktp.source_key",
        quantile_cont(ssn_sum_hit_1pct, 0.25::DOUBLE) AS ssn_q1,
        quantile_cont(ssn_sum_hit_1pct, 0.75::DOUBLE) AS ssn_q3,
        quantile_cont(works_count, 0.25::DOUBLE) AS works_q1,
        quantile_cont(works_count, 0.75::DOUBLE) AS works_q3,
        quantile_cont(cited_by_count, 0.25::DOUBLE) AS cited_q1,
        quantile_cont(cited_by_count, 0.75::DOUBLE) AS cited_q3
    FROM base
    GROUP BY "ktp.source_key"
),

global_bounds AS (
    SELECT
        quantile_cont(ssn_sum_hit_1pct, 0.25::DOUBLE) AS ssn_q1,
        quantile_cont(ssn_sum_hit_1pct, 0.75::DOUBLE) AS ssn_q3,
        quantile_cont(works_count, 0.25::DOUBLE) AS works_q1,
        quantile_cont(works_count, 0.75::DOUBLE) AS works_q3,
        quantile_cont(cited_by_count, 0.25::DOUBLE) AS cited_q1,
        quantile_cont(cited_by_count, 0.75::DOUBLE) AS cited_q3
    FROM base
),

flagged AS (
    SELECT
        b.*,

        (
            b.ssn_sum_hit_1pct < bo.ssn_q1 - 1.5 * (bo.ssn_q3 - bo.ssn_q1)
            OR b.ssn_sum_hit_1pct > bo.ssn_q3 + 1.5 * (bo.ssn_q3 - bo.ssn_q1)
        ) AS ssn_is_tukey_outlier,

        (
            b.works_count < bo.works_q1 - 1.5 * (bo.works_q3 - bo.works_q1)
            OR b.works_count > bo.works_q3 + 1.5 * (bo.works_q3 - bo.works_q1)
        ) AS works_is_tukey_outlier,

        (
            b.cited_by_count < bo.cited_q1 - 1.5 * (bo.cited_q3 - bo.cited_q1)
            OR b.cited_by_count > bo.cited_q3 + 1.5 * (bo.cited_q3 - bo.cited_q1)
        ) AS cited_is_tukey_outlier,

        (
            b.ssn_sum_hit_1pct < gb.ssn_q1 - 1.5 * (gb.ssn_q3 - gb.ssn_q1)
            OR b.ssn_sum_hit_1pct > gb.ssn_q3 + 1.5 * (gb.ssn_q3 - gb.ssn_q1)
            OR b.works_count < gb.works_q1 - 1.5 * (gb.works_q3 - gb.works_q1)
            OR b.works_count > gb.works_q3 + 1.5 * (gb.works_q3 - gb.works_q1)
            OR b.cited_by_count < gb.cited_q1 - 1.5 * (gb.cited_q3 - gb.cited_q1)
            OR b.cited_by_count > gb.cited_q3 + 1.5 * (gb.cited_q3 - gb.cited_q1)
        ) AS global_row_has_tukey_outlier

    FROM base b
    JOIN bounds bo
        ON b."ktp.source_key" = bo."ktp.source_key"
    CROSS JOIN global_bounds gb
),

flagged2 AS (
    SELECT
        *,
        (
            ssn_is_tukey_outlier
            OR works_is_tukey_outlier
            OR cited_is_tukey_outlier
        ) AS row_has_tukey_outlier
    FROM flagged
),

ranked AS (
    SELECT
        *,
        rank() OVER (
            PARTITION BY "ktp.source_key"
            ORDER BY
                CASE WHEN row_has_tukey_outlier THEN 0 ELSE 1 END,
                works_count DESC NULLS LAST,
                ssn_sum_hit_1pct DESC NULLS LAST,
                cited_by_count DESC NULLS LAST
        ) AS max_works_rule_rank
    FROM flagged2
),

grouped AS (
    SELECT
        "ktp.source_key",

        min(ssn_sum_hit_1pct) AS ssn_min,
        quantile_cont(ssn_sum_hit_1pct, 0.20::DOUBLE) AS ssn_q20,
        quantile_cont(ssn_sum_hit_1pct, 0.40::DOUBLE) AS ssn_q40,
        median(ssn_sum_hit_1pct) AS ssn_median,
        quantile_cont(ssn_sum_hit_1pct, 0.60::DOUBLE) AS ssn_q60,
        quantile_cont(ssn_sum_hit_1pct, 0.80::DOUBLE) AS ssn_q80,
        max(ssn_sum_hit_1pct) AS ssn_max,

        min(works_count) AS works_min,
        quantile_cont(works_count, 0.20::DOUBLE) AS works_q20,
        quantile_cont(works_count, 0.40::DOUBLE) AS works_q40,
        median(works_count) AS works_median,
        quantile_cont(works_count, 0.60::DOUBLE) AS works_q60,
        quantile_cont(works_count, 0.80::DOUBLE) AS works_q80,
        max(works_count) AS works_max,

        min(cited_by_count) AS cited_min,
        quantile_cont(cited_by_count, 0.20::DOUBLE) AS cited_q20,
        quantile_cont(cited_by_count, 0.40::DOUBLE) AS cited_q40,
        median(cited_by_count) AS cited_median,
        quantile_cont(cited_by_count, 0.60::DOUBLE) AS cited_q60,
        quantile_cont(cited_by_count, 0.80::DOUBLE) AS cited_q80,
        max(cited_by_count) AS cited_max,

        count(*) FILTER (WHERE row_has_tukey_outlier) AS tukey_outlier_row_count,
        count(*) FILTER (WHERE global_row_has_tukey_outlier) AS global_tukey_outlier_row_count,

        count("ktp.fragment") AS authorid_count,
        
        coalesce(
            to_json(list("ktp.fragment" ORDER BY works_count DESC NULLS LAST, "ktp.fragment") FILTER (WHERE "ktp.fragment" IS NOT NULL)),
            json('[]')
        ) AS authorids_json,

        coalesce(to_json(list("ktp.fragment" ORDER BY works_count DESC NULLS LAST, "ktp.fragment") FILTER (WHERE ssn_is_tukey_outlier)), json('[]'))
            AS ssn_sum_hit_1pct_tukey_fragments_json,

        coalesce(to_json(list("ktp.fragment" ORDER BY works_count DESC NULLS LAST, "ktp.fragment") FILTER (WHERE works_is_tukey_outlier)), json('[]'))
            AS works_count_tukey_fragments_json,

        coalesce(to_json(list("ktp.fragment" ORDER BY works_count DESC NULLS LAST, "ktp.fragment") FILTER (WHERE cited_is_tukey_outlier)), json('[]'))
            AS cited_by_count_tukey_fragments_json,

        CASE
            WHEN count(*) FILTER (WHERE ssn_is_tukey_outlier) = 1
                THEN max("ktp.fragment") FILTER (WHERE ssn_is_tukey_outlier)
            WHEN count(*) FILTER (WHERE cited_is_tukey_outlier) = 1
                THEN max("ktp.fragment") FILTER (WHERE cited_is_tukey_outlier)
            WHEN count(*) FILTER (WHERE works_is_tukey_outlier) = 1
                THEN max("ktp.fragment") FILTER (WHERE works_is_tukey_outlier)
            ELSE NULL
        END AS tukey_priority_selected_fragment,

        CASE
            WHEN count(*) FILTER (
                WHERE row_has_tukey_outlier
                  AND max_works_rule_rank = 1
            ) = 1
                THEN max("ktp.fragment") FILTER (
                    WHERE row_has_tukey_outlier
                      AND max_works_rule_rank = 1
                )
            ELSE NULL
        END AS max_works_rule_selected_fragment,

        count(*) FILTER (WHERE row_has_tukey_outlier) <> 1 AS flag

    FROM ranked
    GROUP BY "ktp.source_key"
)

SELECT
    *,
    tukey_priority_selected_fragment IS NOT DISTINCT FROM max_works_rule_selected_fragment
        AS selected_fragments_same
FROM grouped
ORDER BY "ktp.source_key";
