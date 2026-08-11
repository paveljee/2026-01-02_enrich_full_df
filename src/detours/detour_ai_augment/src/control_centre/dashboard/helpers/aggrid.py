from __future__ import annotations

from typing import Any, Final


class AgGrid:
    COLUMN_DEFINITIONS_OPTION: Final = "columnDefs"
    ROW_DATA_OPTION: Final = "rowData"
    DEFAULT_COLUMN_DEFINITION_OPTION: Final = "defaultColDef"
    GET_ROW_ID_OPTION: Final = ":getRowId"
    ENABLE_CELL_TEXT_SELECTION_OPTION: Final = "enableCellTextSelection"
    ENSURE_DOM_ORDER_OPTION: Final = "ensureDomOrder"

    SET_GRID_OPTION_METHOD: Final = "setGridOption"
    UPDATE_DATA_METHOD: Final = "updateData"

    COLUMN_FIELD: Final = "field"
    COLUMN_HEADER_NAME: Final = "headerName"
    COLUMN_WIDTH: Final = "width"
    COLUMN_COMPARATOR: Final = ":comparator"
    COLUMN_WRAP_TEXT: Final = "wrapText"
    COLUMN_AUTO_HEIGHT: Final = "autoHeight"
    COLUMN_RESIZABLE: Final = "resizable"
    COLUMN_SORTABLE: Final = "sortable"
    COLUMN_FILTER: Final = "filter"

    CELL_CLICKED_EVENT: Final = "cellClicked"
    EVENT_DATA: Final = "data"
    GET_ROW_ID_TEMPLATE: Final = "params => params.data.{row_id_field}"

    DRAW_COMPARATOR: Final = r"""(valueA, valueB) => {
        const key = value => {
            const raw = String(value || '').split(',')[0].trim().toLowerCase();
            const pilot = raw.startsWith('pilot.');
            const body = pilot ? raw.slice('pilot.'.length) : raw;
            const group = pilot ? 0 : (/^\d+$/.test(raw) ? 1 : (raw ? 2 : 3));
            const parts = (body.match(/\d+|\D+/g) || []).map(
                part => /^\d+$/.test(part) ? [0, Number(part)] : [1, part]
            );
            return [group, parts, raw];
        };
        const compare = (left, right) => {
            if (left[0] !== right[0]) return left[0] - right[0];
            const length = Math.max(left[1].length, right[1].length);
            for (let index = 0; index < length; index += 1) {
                if (index >= left[1].length) return -1;
                if (index >= right[1].length) return 1;
                if (left[1][index][0] !== right[1][index][0]) {
                    return left[1][index][0] - right[1][index][0];
                }
                if (left[1][index][1] < right[1][index][1]) return -1;
                if (left[1][index][1] > right[1][index][1]) return 1;
            }
            return left[2].localeCompare(right[2]);
        };
        return compare(key(valueA), key(valueB));
    }"""

    @classmethod
    def column(
        cls,
        *,
        field: str,
        header: str,
        width: int,
        comparator: str | None = None,
        wrap_text: bool = False,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            cls.COLUMN_FIELD: field,
            cls.COLUMN_HEADER_NAME: header,
            cls.COLUMN_WIDTH: width,
        }
        if comparator is not None:
            result[cls.COLUMN_COMPARATOR] = comparator
        if wrap_text:
            result[cls.COLUMN_WRAP_TEXT] = True
            result[cls.COLUMN_AUTO_HEIGHT] = True
        return result

    @classmethod
    def options(
        cls,
        *,
        columns: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        row_id_field: str,
    ) -> dict[str, Any]:
        return {
            cls.COLUMN_DEFINITIONS_OPTION: columns,
            cls.ROW_DATA_OPTION: rows,
            cls.DEFAULT_COLUMN_DEFINITION_OPTION: {
                cls.COLUMN_RESIZABLE: True,
                cls.COLUMN_SORTABLE: True,
                cls.COLUMN_FILTER: True,
            },
            cls.GET_ROW_ID_OPTION: cls.GET_ROW_ID_TEMPLATE.format(
                row_id_field=row_id_field
            ),
            cls.ENABLE_CELL_TEXT_SELECTION_OPTION: True,
            cls.ENSURE_DOM_ORDER_OPTION: True,
        }
