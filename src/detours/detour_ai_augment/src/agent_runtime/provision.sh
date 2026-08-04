#!/bin/bash
set -euo pipefail

AIVM_USER="${AIVM_USER:-ai}"
AIVM_HOME="${AIVM_HOME:-/home/$AIVM_USER}"
AIVM_AUTHORIZED_KEY="${AIVM_AUTHORIZED_KEY:-}"
AIVM_RESTRICTED_PATH="${AIVM_RESTRICTED_PATH:-}"
AIVM_SSH_PORT="${AIVM_SSH_PORT:-22022}"
AIVM_SSH_SERVER_NAME="aivm-sshd.service"
AIVM_SSH_SERVER_DESCRIPTION="AIVM private SSH server"
AIVM_SERVICE_RESTART_SECONDS="2"

AIVM_VSCODE_VERSION="${AIVM_VSCODE_VERSION:-1.130.0}"
AIVM_VSCODE_COMMIT="${AIVM_VSCODE_COMMIT:-1b6a188127eeaf9194f945eb6eb89a657e93c54c}"
AIVM_VSCODE_URL="${AIVM_VSCODE_URL:-https://update.code.visualstudio.com/commit:$AIVM_VSCODE_COMMIT/server-linux-arm64/stable}"
AIVM_VSCODE_PATH="${AIVM_VSCODE_PATH:-$AIVM_HOME/.vscode-server/bin/$AIVM_VSCODE_COMMIT}"
AIVM_VSCODE_BIN_PATH="${AIVM_VSCODE_BIN_PATH:-$AIVM_VSCODE_PATH/bin/code-server}"
AIVM_VSCE_PATH="${AIVM_VSCE_PATH:-$AIVM_HOME/.vscode-server/extensions}"
AIVM_CODEX_VSCE="${AIVM_CODEX_VSCE:-openai.chatgpt@26.721.41059}"
AIVM_CODEX_PATH="${AIVM_CODEX_PATH:-$AIVM_HOME/.codex}"
AIVM_CODEX_SESSIONS_PATH="$AIVM_CODEX_PATH/sessions"
AIVM_CODEX_CONFIG_PATH="${AIVM_CODEX_CONFIG_PATH:-$AIVM_CODEX_PATH/config.toml}"
AIVM_APPENDWATCH_SCRIPT="${AIVM_APPENDWATCH_SCRIPT:-}"
AIVM_APPENDWATCH_REPORT="${AIVM_APPENDWATCH_REPORT:-}"
APPENDWATCH_DIR="$(dirname "$AIVM_APPENDWATCH_SCRIPT")"
AIVM_APPENDWATCH_SERVICE_NAME="aivm-appendwatch.service"
AIVM_APPENDWATCH_SERVICE_DESCRIPTION="AIVM Codex rollout append-only watcher"
AIVM_APPENDWATCH_REPORT_WAIT_ATTEMPTS="50"
AIVM_APPENDWATCH_REPORT_WAIT_INTERVAL_SECONDS="0.1"

usage() {
    cat <<EOF
Usage:
  sudo $0 \\
    --authorized-key-file /path/to/id_ed25519.pub \\
    --restricted-path /absolute/guest/mount/path

Options:
  --user NAME
  --home PATH
  --authorized-key KEY
  --authorized-key-file PATH
  --restricted-path PATH
  --ssh-port PORT
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --user)
            [ -n "${2:-}" ] || { echo "❌ Missing user"; exit 1; }
            AIVM_USER="$2"
            shift 2
            ;;
        --home)
            [ -n "${2:-}" ] || { echo "❌ Missing home"; exit 1; }
            AIVM_HOME="$2"
            shift 2
            ;;
        --authorized-key)
            [ -n "${2:-}" ] || { echo "❌ Missing authorized key"; exit 1; }
            AIVM_AUTHORIZED_KEY="$2"
            shift 2
            ;;
        --authorized-key-file)
            [ -n "${2:-}" ] || { echo "❌ Missing authorized key file"; exit 1; }
            AIVM_AUTHORIZED_KEY="$(cat "$2")"
            shift 2
            ;;
        --restricted-path)
            [ -n "${2:-}" ] || { echo "❌ Missing restricted path"; exit 1; }
            AIVM_RESTRICTED_PATH="$2"
            shift 2
            ;;
        --ssh-port)
            [ -n "${2:-}" ] || { echo "❌ Missing SSH port"; exit 1; }
            AIVM_SSH_PORT="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "❌ Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

[ "$(id -u)" -eq 0 ] \
    || { echo "❌ This provisioning script must run as root"; exit 1; }

[[ "$AIVM_USER" =~ ^[a-z_][a-z0-9_-]*\$?$ ]] \
    || { echo "❌ Invalid user name: $AIVM_USER"; exit 1; }

case "$AIVM_HOME" in
    /*) ;;
    *) echo "❌ Home must be an absolute path: $AIVM_HOME"; exit 1 ;;
esac

case "$AIVM_RESTRICTED_PATH" in
    /*) ;;
    "") echo "❌ Restricted path is required"; exit 1 ;;
    *) echo "❌ Restricted path must be absolute: $AIVM_RESTRICTED_PATH"; exit 1 ;;
esac

case "$AIVM_APPENDWATCH_SCRIPT" in
    "$AIVM_RESTRICTED_PATH"/*) ;;
    "") echo "❌ Appendwatch script path is required"; exit 1 ;;
    *) echo "❌ Appendwatch script must be below the restricted path"; exit 1 ;;
esac

case "$AIVM_APPENDWATCH_REPORT" in
    "$AIVM_RESTRICTED_PATH"/*) ;;
    "") echo "❌ Appendwatch report path is required"; exit 1 ;;
    *) echo "❌ Appendwatch report must be below the restricted path"; exit 1 ;;
esac

case "$AIVM_AUTHORIZED_KEY" in
    ssh-*) ;;
    "") echo "❌ Authorized key is required"; exit 1 ;;
    *) echo "❌ Authorized key does not look like an SSH public key"; exit 1 ;;
esac

[[ "$AIVM_SSH_PORT" =~ ^[0-9]+$ ]] \
    && [ "$AIVM_SSH_PORT" -ge 1 ] \
    && [ "$AIVM_SSH_PORT" -le 65535 ] \
    || { echo "❌ Invalid SSH port: $AIVM_SSH_PORT"; exit 1; }

RESTRICTED_GATE="$(dirname "$AIVM_RESTRICTED_PATH")"
[ "$RESTRICTED_GATE" != "/" ] \
    || { echo "❌ Refusing to restrict filesystem root"; exit 1; }

case "$AIVM_HOME/" in
    "$RESTRICTED_GATE/"*)
        echo "❌ Restricted-path parent contains the AIVM home: $RESTRICTED_GATE"
        exit 1
        ;;
esac

packages=()
command -v setfacl >/dev/null 2>&1 || packages+=(acl)
command -v sshd >/dev/null 2>&1 || packages+=(openssh-server)
command -v curl >/dev/null 2>&1 || packages+=(curl)
command -v openssl >/dev/null 2>&1 || packages+=(openssl)
[ -f /etc/ssl/certs/ca-certificates.crt ] || packages+=(ca-certificates)

if [ "${#packages[@]}" -gt 0 ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends "${packages[@]}"
fi

if ! getent group "$AIVM_USER" >/dev/null; then
    groupadd "$AIVM_USER"
fi

if ! id -u "$AIVM_USER" >/dev/null 2>&1; then
    useradd \
        --create-home \
        --home-dir "$AIVM_HOME" \
        --shell /bin/bash \
        --gid "$AIVM_USER" \
        "$AIVM_USER"
else
    usermod \
        --home "$AIVM_HOME" \
        --shell /bin/bash \
        "$AIVM_USER"
fi

AIVM_GROUP="$(id -gn "$AIVM_USER")"

# Keep the AIVM user non-sudo.
for group in sudo admin wheel; do
    if getent group "$group" >/dev/null; then
        gpasswd -d "$AIVM_USER" "$group" >/dev/null 2>&1 || true
    fi
done
rm -f "/etc/sudoers.d/$AIVM_USER"

# Keep the account unlocked for public-key SSH, but assign an unknown random
# password while password authentication remains disabled.
AIVM_RANDOM_PASSWORD="$(
    head -c 48 /dev/urandom |
        base64 |
        tr -d '\n'
)"
AIVM_PASSWORD_HASH="$(
    printf '%s' "$AIVM_RANDOM_PASSWORD" |
        openssl passwd -6 -stdin
)"
unset AIVM_RANDOM_PASSWORD
usermod --password "$AIVM_PASSWORD_HASH" "$AIVM_USER"
unset AIVM_PASSWORD_HASH

install -d \
    -m 0700 \
    -o "$AIVM_USER" \
    -g "$AIVM_GROUP" \
    "$AIVM_HOME"

install -d \
    -m 0700 \
    -o "$AIVM_USER" \
    -g "$AIVM_GROUP" \
    "$AIVM_HOME/.ssh"

printf '%s\n' "$AIVM_AUTHORIZED_KEY" > "$AIVM_HOME/.ssh/authorized_keys"
chown "$AIVM_USER:$AIVM_GROUP" "$AIVM_HOME/.ssh/authorized_keys"
chmod 0600 "$AIVM_HOME/.ssh/authorized_keys"

# Preserve the normal Lima mount, but deny this user even directory traversal.
mkdir -p "$RESTRICTED_GATE"
setfacl -m "u:$AIVM_USER:---" "$RESTRICTED_GATE"

if runuser -u "$AIVM_USER" -- \
    bash -c 'cd -- "$1" >/dev/null 2>&1' bash "$RESTRICTED_GATE"; then
    echo "❌ Failed to block '$AIVM_USER' from traversing: $RESTRICTED_GATE"
    exit 1
fi

install -d \
    -m 0700 \
    -o "$AIVM_USER" \
    -g "$AIVM_GROUP" \
    "$AIVM_CODEX_PATH" \
    "$AIVM_CODEX_SESSIONS_PATH"

# Start appendwatch before anything Codex-capable runs as the AIVM user.
chmod 0700 "$APPENDWATCH_DIR"
chmod 0600 "$AIVM_APPENDWATCH_SCRIPT"

cat > "/etc/systemd/system/$AIVM_APPENDWATCH_SERVICE_NAME" <<EOF
[Unit]
Description="$AIVM_APPENDWATCH_SERVICE_DESCRIPTION"
After=local-fs.target
RequiresMountsFor="$AIVM_APPENDWATCH_SCRIPT" "$AIVM_CODEX_SESSIONS_PATH"

[Service]
Type=simple
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 -B "$AIVM_APPENDWATCH_SCRIPT" "$AIVM_CODEX_SESSIONS_PATH" --report "$AIVM_APPENDWATCH_REPORT"
Restart=on-failure
RestartSec=$AIVM_SERVICE_RESTART_SECONDS

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$AIVM_APPENDWATCH_SERVICE_NAME"
systemctl is-enabled --quiet "$AIVM_APPENDWATCH_SERVICE_NAME"
systemctl is-active --quiet "$AIVM_APPENDWATCH_SERVICE_NAME"

for ((attempt = 0; attempt < AIVM_APPENDWATCH_REPORT_WAIT_ATTEMPTS; attempt++)); do
    [ -s "$AIVM_APPENDWATCH_REPORT" ] && break
    sleep "$AIVM_APPENDWATCH_REPORT_WAIT_INTERVAL_SECONDS"
done
[ -s "$AIVM_APPENDWATCH_REPORT" ] \
    || { echo "❌ Appendwatch did not create its report"; exit 1; }

# Everything below runs as the unprivileged AIVM user.
runuser -u "$AIVM_USER" -- env \
    HOME="$AIVM_HOME" \
    USER="$AIVM_USER" \
    LOGNAME="$AIVM_USER" \
    AIVM_VSCODE_URL="$AIVM_VSCODE_URL" \
    AIVM_VSCODE_PATH="$AIVM_VSCODE_PATH" \
    AIVM_VSCODE_BIN_PATH="$AIVM_VSCODE_BIN_PATH" \
    AIVM_VSCE_PATH="$AIVM_VSCE_PATH" \
    AIVM_CODEX_VSCE="$AIVM_CODEX_VSCE" \
    AIVM_CODEX_PATH="$AIVM_CODEX_PATH" \
    AIVM_CODEX_SESSIONS_PATH="$AIVM_CODEX_SESSIONS_PATH" \
    AIVM_CODEX_CONFIG_PATH="$AIVM_CODEX_CONFIG_PATH" \
    bash <<'AIVM_USER_PROVISION'
set -euo pipefail

chmod 700 "$AIVM_CODEX_PATH"
cat > "$AIVM_CODEX_CONFIG_PATH" <<'CODEX_CONFIG'
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
personality = "none"
web_search = "live"
sandbox_mode = "danger-full-access"
approval_policy = "never"
service_tier = "default"

[agents]
enabled = false

[sandbox_workspace_write]
network_access = true
CODEX_CONFIG
chmod 600 "$AIVM_CODEX_CONFIG_PATH"

mkdir -p "$AIVM_VSCODE_PATH"
if [ ! -x "$AIVM_VSCODE_BIN_PATH" ]; then
    curl -fsSL "$AIVM_VSCODE_URL" |
        tar -xz --strip-components=1 -C "$AIVM_VSCODE_PATH"
fi

mkdir -p "$AIVM_VSCE_PATH"
"$AIVM_VSCODE_BIN_PATH" \
    --extensions-dir "$AIVM_VSCE_PATH" \
    --install-extension "$AIVM_CODEX_VSCE" --force
AIVM_USER_PROVISION

# The normal Lima sshd must never accept this account.
cat > /etc/ssh/sshd_config.d/90-aivm-deny.conf <<EOF
DenyUsers $AIVM_USER
EOF

/usr/sbin/sshd -t
systemctl reload ssh.service 2>/dev/null \
    || systemctl reload sshd.service

# Run a second sshd only on guest loopback for the AIVM account.
install -d -m 0700 /etc/ssh/aivm
if [ ! -f /etc/ssh/aivm/ssh_host_ed25519_key ]; then
    ssh-keygen \
        -q \
        -t ed25519 \
        -N "" \
        -f /etc/ssh/aivm/ssh_host_ed25519_key
fi

cat > /etc/ssh/sshd_config_aivm <<EOF
Port $AIVM_SSH_PORT
ListenAddress 127.0.0.1
AddressFamily inet

HostKey /etc/ssh/aivm/ssh_host_ed25519_key
PidFile /run/sshd-aivm.pid

UsePAM yes
StrictModes yes
PubkeyAuthentication yes
AuthenticationMethods publickey
AuthorizedKeysFile $AIVM_HOME/.ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitEmptyPasswords no
PermitRootLogin no
AllowUsers $AIVM_USER

AllowAgentForwarding no
# For VS Code to be able to connect
AllowTcpForwarding local
PermitOpen 127.0.0.1:*
AllowStreamLocalForwarding no
GatewayPorts no
X11Forwarding no
PermitTunnel no
PermitUserEnvironment no
PermitTTY yes

PrintMotd no
PrintLastLog yes
TCPKeepAlive yes
Subsystem sftp internal-sftp
EOF

cat > "/etc/systemd/system/$AIVM_SSH_SERVER_NAME" <<EOF
[Unit]
Description=$AIVM_SSH_SERVER_DESCRIPTION
After=network.target ssh.service

[Service]
Type=simple
ExecStartPre=/usr/sbin/sshd -t -f /etc/ssh/sshd_config_aivm
ExecStart=/usr/sbin/sshd -D -e -f /etc/ssh/sshd_config_aivm
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=process
Restart=on-failure
RestartSec=$AIVM_SERVICE_RESTART_SECONDS

[Install]
WantedBy=multi-user.target
EOF

/usr/sbin/sshd -t -f /etc/ssh/sshd_config_aivm
systemctl daemon-reload
systemctl enable --now "$AIVM_SSH_SERVER_NAME"
systemctl restart "$AIVM_SSH_SERVER_NAME"

if command -v sudo >/dev/null 2>&1 \
    && runuser -u "$AIVM_USER" -- sudo -n true >/dev/null 2>&1; then
    echo "❌ '$AIVM_USER' unexpectedly has passwordless sudo"
    exit 1
fi

echo "✅ Provisioned '$AIVM_USER' with private SSH access on 127.0.0.1:$AIVM_SSH_PORT"
