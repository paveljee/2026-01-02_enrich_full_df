#!/bin/bash
set -e

SCRIPT_NAME="aivm"
PROVISION_LIB_NAME="provision.sh"
APPENDWATCH_LIB_NAME="appendwatch.py"
INSTALL_PATH="$HOME/.local/bin/$SCRIPT_NAME"
INSTALL_LIB_DIR="$HOME/.local/lib/$SCRIPT_NAME"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="/Volumes/home/aicode/aivm/home/ai"
LIMA_INSTANCE="aivm"
MOUNT_DIR="$PROJECT_DIR"
# Though using the real --mount dir downstream to preserve macOS paths
DEFAULT_MOUNTPOINT="$PROJECT_DIR"
GUEST_MOUNTPOINT="$DEFAULT_MOUNTPOINT"
AIVM_USER="ai"
AIVM_HOME="/home/$AIVM_USER"
AIVM_SSH_PORT="22022"
AIVM_BACKEND_PORT="8612"
AIVM_KEY_DIR="$HOME/.local/share/$SCRIPT_NAME/.ssh"
AIVM_IDENTITY_FILE="$AIVM_KEY_DIR/id_ed25519"
AIVM_KNOWN_HOSTS_FILE="$AIVM_KEY_DIR/known_hosts"
AIVM_SSH_TARGET="$LIMA_INSTANCE-$AIVM_USER"
AIVM_HOST_KEY_ALIAS="lima-$LIMA_INSTANCE-$AIVM_USER"
AIVM_SSH_CMD=()

# Codex etc. config to ship with AIVM
VSCODE_VERSION="1.130.0"
VSCODE_COMMIT="1b6a188127eeaf9194f945eb6eb89a657e93c54c"
VSCODE_URL="https://update.code.visualstudio.com/commit:$VSCODE_COMMIT/server-linux-arm64/stable"
VSCODE_PATH="$AIVM_HOME/.vscode-server/bin/$VSCODE_COMMIT"
VSCODE_BIN_PATH="$VSCODE_PATH/bin/code-server"
VSCE_PATH="$AIVM_HOME/.vscode-server/extensions"
CODEX_VSCE_VERSION="26.721.41059"
CODEX_VSCE="openai.chatgpt@$CODEX_VSCE_VERSION"
CODEX_CLI_VERSION="0.146.0-alpha.3.1"
CODEX_CLI_INSTALL_URL="https://chatgpt.com/codex/install.sh"
CODEX_CLI_BIN_PATH="$AIVM_HOME/.local/bin/codex"
CODEX_PATH="$AIVM_HOME/.codex"
CODEX_CONFIG_PATH="$CODEX_PATH/config.toml"

if [ "$0" = "$INSTALL_PATH" ]; then
    PROVISION_SCRIPT="$INSTALL_LIB_DIR/$PROVISION_LIB_NAME"
    APPENDWATCH_SCRIPT="$INSTALL_LIB_DIR/$APPENDWATCH_LIB_NAME"
else
    PROVISION_SCRIPT="${AIVM_PROVISION_SCRIPT:-$SOURCE_DIR/$PROVISION_LIB_NAME}"
    APPENDWATCH_SCRIPT="${AIVM_APPENDWATCH_SCRIPT:-$SOURCE_DIR/../control_centre/appendwatch/$APPENDWATCH_LIB_NAME}"
fi

prepare_mount_paths() {
    AIVM_CONTROL_DIR="$MOUNT_DIR/.aivm-control/appendwatch"
    GUEST_CONTROL_DIR="$GUEST_MOUNTPOINT/.aivm-control/appendwatch"
    GUEST_APPENDWATCH_SCRIPT="$GUEST_CONTROL_DIR/$APPENDWATCH_LIB_NAME"
    GUEST_APPENDWATCH_REPORT="$GUEST_CONTROL_DIR/appendwatch-tree.txt"
    HOST_APPENDWATCH_REPORT="$AIVM_CONTROL_DIR/appendwatch-tree.txt"
}

# Self-install function
self_install() {
    if [ "$0" != "$INSTALL_PATH" ]; then
        [ -f "$PROVISION_SCRIPT" ] \
            || { echo "❌ Provisioning script not found: $PROVISION_SCRIPT"; exit 1; }
        [ -f "$APPENDWATCH_SCRIPT" ] \
            || { echo "❌ Appendwatch script not found: $APPENDWATCH_SCRIPT"; exit 1; }

        echo "📦 Installing $SCRIPT_NAME to $INSTALL_PATH..."
        mkdir -p "$HOME/.local/bin" "$INSTALL_LIB_DIR"
        cp "$0" "$INSTALL_PATH"
        cp "$PROVISION_SCRIPT" "$INSTALL_LIB_DIR/$PROVISION_LIB_NAME"
        cp "$APPENDWATCH_SCRIPT" "$INSTALL_LIB_DIR/$APPENDWATCH_LIB_NAME"
        chmod +x "$INSTALL_PATH" "$INSTALL_LIB_DIR/$PROVISION_LIB_NAME"
        chmod 600 "$INSTALL_LIB_DIR/$APPENDWATCH_LIB_NAME"
        echo "✅ Installed! You can now run: $SCRIPT_NAME"
        echo "💡 Make sure $HOME/.local/bin is in your PATH"

        # Check if in PATH
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            echo "⚠️  Add this to your ~/.zshrc or ~/.bashrc:"
            echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
        fi
        exit 0
    fi
}

base64_string() {
    printf '%s' "$1" | base64 | tr -d '\n'
}

base64_file() {
    base64 < "$1" | tr -d '\n'
}

yaml_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
}

generate_aivm_key() {
    rm -rf "$AIVM_KEY_DIR"
    mkdir -p "$AIVM_KEY_DIR"
    chmod 700 "$AIVM_KEY_DIR"

    ssh-keygen \
        -q \
        -t ed25519 \
        -N "" \
        -C "$LIMA_INSTANCE:$AIVM_USER" \
        -f "$AIVM_IDENTITY_FILE"

    chmod 600 "$AIVM_IDENTITY_FILE"
    chmod 644 "$AIVM_IDENTITY_FILE.pub"
    : > "$AIVM_KNOWN_HOSTS_FILE"
    chmod 600 "$AIVM_KNOWN_HOSTS_FILE"
}

remove_aivm_key() {
    rm -rf "$AIVM_KEY_DIR"
}

prepare_aivm_ssh() {
    LIMA_SSH_CONFIG_PATH="$HOME/.lima/$LIMA_INSTANCE/ssh.config"

    AIVM_SSH_CMD=(
        ssh
        -F "$LIMA_SSH_CONFIG_PATH"
        -o "ProxyJump=lima-$LIMA_INSTANCE"
        -o "HostName=127.0.0.1"
        -o "Port=$AIVM_SSH_PORT"
        -o "User=$AIVM_USER"
        -o "IdentityFile=$AIVM_IDENTITY_FILE"
        -o "IdentitiesOnly=yes"
        -o "BatchMode=yes"
        -o "PasswordAuthentication=no"
        -o "KbdInteractiveAuthentication=no"
        -o "ForwardAgent=no"
        -o "ClearAllForwardings=no"
        -o "UserKnownHostsFile=$AIVM_KNOWN_HOSTS_FILE"
        -o "HostKeyAlias=$AIVM_HOST_KEY_ALIAS"
        -o "StrictHostKeyChecking=accept-new"
    )
}

aivm_ssh() {
    "${AIVM_SSH_CMD[@]}" "$AIVM_SSH_TARGET" "$@"
}

# Parse flags in any order
while [ "$#" -gt 0 ]; do
    case "$1" in
        --install)
            self_install
            shift
            ;;
        --mount)
            [ -n "${2:-}" ] || { echo "❌ Missing mount path"; exit 1; }
            MOUNT_DIR="$(cd "$2" && pwd -P)"
            GUEST_MOUNTPOINT="$MOUNT_DIR"
            shift 2
            ;;
        *)
            echo "❌ Unknown option: $1"
            exit 1
            ;;
    esac
done

prepare_mount_paths

[ -f "$PROVISION_SCRIPT" ] \
    || { echo "❌ Provisioning script not found: $PROVISION_SCRIPT"; exit 1; }
[ -f "$APPENDWATCH_SCRIPT" ] \
    || { echo "❌ Appendwatch script not found: $APPENDWATCH_SCRIPT"; exit 1; }

# Navigate to project directory
cd "$MOUNT_DIR" || { echo "❌ Directory not found: $MOUNT_DIR"; exit 1; }

# Always recreate the AIVM instance but prompt to be sure
if limactl list | grep -q "^$LIMA_INSTANCE"; then
    echo "♻️ Recreating Lima instance '$LIMA_INSTANCE'..."
    read -r -p "⚠️ Delete Lima instance '$LIMA_INSTANCE'? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS])
            limactl delete -f "$LIMA_INSTANCE"
            echo "🗑️ Removed instance '$LIMA_INSTANCE' from Lima"
            remove_aivm_key
            echo "🗑️ Removed '$AIVM_KEY_DIR' containing '$AIVM_USER' SSH key"

            ;;
        *)
            echo "❌ Use existing instance with \`limactl shell $LIMA_INSTANCE\`"
            exit 0
            ;;
    esac
fi

mkdir -p "$AIVM_CONTROL_DIR"
chmod 700 "$AIVM_CONTROL_DIR"
cp "$APPENDWATCH_SCRIPT" "$AIVM_CONTROL_DIR/$APPENDWATCH_LIB_NAME"
chmod 600 "$AIVM_CONTROL_DIR/$APPENDWATCH_LIB_NAME"

echo "🔑 Generating a dedicated SSH key for '$AIVM_USER' into '$AIVM_KEY_DIR'..."
generate_aivm_key

echo "🚀 Creating new Lima instance '$LIMA_INSTANCE'..."

PROVISION_SCRIPT_B64="$(base64_file "$PROVISION_SCRIPT")"
AIVM_USER_B64="$(base64_string "$AIVM_USER")"
AIVM_HOME_B64="$(base64_string "$AIVM_HOME")"
AIVM_AUTHORIZED_KEY_B64="$(base64_file "$AIVM_IDENTITY_FILE.pub")"
AIVM_RESTRICTED_PATH_B64="$(base64_string "$GUEST_MOUNTPOINT")"
AIVM_SSH_PORT_B64="$(base64_string "$AIVM_SSH_PORT")"
AIVM_BACKEND_PORT_B64="$(base64_string "$AIVM_BACKEND_PORT")"
VSCODE_VERSION_B64="$(base64_string "$VSCODE_VERSION")"
VSCODE_COMMIT_B64="$(base64_string "$VSCODE_COMMIT")"
VSCODE_URL_B64="$(base64_string "$VSCODE_URL")"
VSCODE_PATH_B64="$(base64_string "$VSCODE_PATH")"
VSCODE_BIN_PATH_B64="$(base64_string "$VSCODE_BIN_PATH")"
VSCE_PATH_B64="$(base64_string "$VSCE_PATH")"
CODEX_VSCE_B64="$(base64_string "$CODEX_VSCE")"
CODEX_CLI_VERSION_B64="$(base64_string "$CODEX_CLI_VERSION")"
CODEX_CLI_INSTALL_URL_B64="$(base64_string "$CODEX_CLI_INSTALL_URL")"
CODEX_CLI_BIN_PATH_B64="$(base64_string "$CODEX_CLI_BIN_PATH")"
CODEX_PATH_B64="$(base64_string "$CODEX_PATH")"
CODEX_CONFIG_PATH_B64="$(base64_string "$CODEX_CONFIG_PATH")"
APPENDWATCH_SCRIPT_B64="$(base64_string "$GUEST_APPENDWATCH_SCRIPT")"
APPENDWATCH_REPORT_B64="$(base64_string "$GUEST_APPENDWATCH_REPORT")"

MOUNT_DIR_YAML="$(yaml_escape "$MOUNT_DIR")"
GUEST_MOUNTPOINT_YAML="$(yaml_escape "$GUEST_MOUNTPOINT")"

# Create a minimal Lima template for Apple Silicon
cat > /tmp/aivm.yaml <<EOF
# Minimal aivm configuration for Apple Silicon
images:
  - location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
    arch: "aarch64"

# ONLY mount the project directory - no defaults
mounts:
  - location: "$MOUNT_DIR_YAML"
    mountPoint: "$GUEST_MOUNTPOINT_YAML"
    writable: true

mountType: "reverse-sshfs"

# Do not load arbitrary host keys or forward the host SSH agent.
ssh:
  loadDotSSHPubKeys: false
  forwardAgent: false

# The private AIVM sshd is reachable only through the Lima SSH jump host.
portForwards:
  - guestIP: "127.0.0.1"
    guestPort: $AIVM_SSH_PORT
    proto: tcp
    ignore: true

cpus: 4
memory: "4GiB"
disk: "10GiB"

provision:
  - mode: system
    script: |
      #!/bin/bash
      set -euo pipefail

      decode() {
          printf '%s' "\$1" | base64 -d
      }

      PROVISION_SCRIPT_PATH="/tmp/$PROVISION_LIB_NAME"
      decode "$PROVISION_SCRIPT_B64" > "\$PROVISION_SCRIPT_PATH"
      chmod 700 "\$PROVISION_SCRIPT_PATH"

      export AIVM_USER="\$(decode "$AIVM_USER_B64")"
      export AIVM_HOME="\$(decode "$AIVM_HOME_B64")"
      export AIVM_AUTHORIZED_KEY="\$(decode "$AIVM_AUTHORIZED_KEY_B64")"
      export AIVM_RESTRICTED_PATH="\$(decode "$AIVM_RESTRICTED_PATH_B64")"
      export AIVM_SSH_PORT="\$(decode "$AIVM_SSH_PORT_B64")"
      export AIVM_BACKEND_PORT="\$(decode "$AIVM_BACKEND_PORT_B64")"
      export AIVM_VSCODE_VERSION="\$(decode "$VSCODE_VERSION_B64")"
      export AIVM_VSCODE_COMMIT="\$(decode "$VSCODE_COMMIT_B64")"
      export AIVM_VSCODE_URL="\$(decode "$VSCODE_URL_B64")"
      export AIVM_VSCODE_PATH="\$(decode "$VSCODE_PATH_B64")"
      export AIVM_VSCODE_BIN_PATH="\$(decode "$VSCODE_BIN_PATH_B64")"
      export AIVM_VSCE_PATH="\$(decode "$VSCE_PATH_B64")"
      export AIVM_CODEX_VSCE="\$(decode "$CODEX_VSCE_B64")"
      export AIVM_CODEX_CLI_VERSION="\$(decode "$CODEX_CLI_VERSION_B64")"
      export AIVM_CODEX_CLI_INSTALL_URL="\$(decode "$CODEX_CLI_INSTALL_URL_B64")"
      export AIVM_CODEX_CLI_BIN_PATH="\$(decode "$CODEX_CLI_BIN_PATH_B64")"
      export AIVM_CODEX_PATH="\$(decode "$CODEX_PATH_B64")"
      export AIVM_CODEX_CONFIG_PATH="\$(decode "$CODEX_CONFIG_PATH_B64")"
      export AIVM_APPENDWATCH_SCRIPT="\$(decode "$APPENDWATCH_SCRIPT_B64")"
      export AIVM_APPENDWATCH_REPORT="\$(decode "$APPENDWATCH_REPORT_B64")"

      "\$PROVISION_SCRIPT_PATH"
      rm -f "\$PROVISION_SCRIPT_PATH"
EOF

# Start with the minimal template
# No need to prompt because already prompted to delete above
limactl start \
    --yes \
    --name="$LIMA_INSTANCE" \
    /tmp/aivm.yaml

echo "✅ Lima instance created successfully"

prepare_aivm_ssh

verify_instance() {
    LIMA_SSH_CONFIG_PATH="$HOME/.lima/$LIMA_INSTANCE/ssh.config"
    ssh -F "$LIMA_SSH_CONFIG_PATH" "lima-$LIMA_INSTANCE" \
        true \
        || { echo "❌ SSH access to Lima jump host failed"; return 1; }
    echo "✅ SSH access to Lima jump host works"

    aivm_ssh true \
        || { echo "❌ SSH access to '$AIVM_USER' through jump host failed"; return 1; }
    echo "✅ SSH access to '$AIVM_USER' through jump host works"

    [ "$(aivm_ssh 'id -un')" = "$AIVM_USER" ] \
        || { echo "❌ Connected as the wrong user"; return 1; }
    echo "✅ Connected as '$AIVM_USER'"

    [ "$(aivm_ssh 'printf "%s" "$HOME"')" = "$AIVM_HOME" ] \
        || { echo "❌ Incorrect home directory"; return 1; }
    echo "✅ Home is '$AIVM_HOME'"

    if aivm_ssh 'command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1'; then
        echo "❌ '$AIVM_USER' has passwordless sudo"
        return 1
    fi
    echo "✅ '$AIVM_USER' has no passwordless sudo"

    PROBE=".aivm-probe-$$"
    touch "$MOUNT_DIR/$PROBE"
    if ! limactl shell --workdir=/ "$LIMA_INSTANCE" \
        test -f "$GUEST_MOUNTPOINT/$PROBE"; then
        rm -f "$MOUNT_DIR/$PROBE"
        echo "❌ Project directory is not mounted at '$GUEST_MOUNTPOINT'"
        return 1
    fi
    echo "✅ Project directory is mounted at '$GUEST_MOUNTPOINT'"
    if ! limactl shell --workdir=/ "$LIMA_INSTANCE" \
        rm -f "$GUEST_MOUNTPOINT/$PROBE"; then
        rm -f "$MOUNT_DIR/$PROBE"
        echo "❌ Mounted project is not writable for the Lima jump user at '$GUEST_MOUNTPOINT'"
        return 1
    fi
    if [ -e "$MOUNT_DIR/$PROBE" ]; then
        rm -f "$MOUNT_DIR/$PROBE"
        echo "❌ Writes through mounted project are not reflected at '$GUEST_MOUNTPOINT'"
        return 1
    fi
    echo "✅ Mounted project is writable for the Lima jump user at '$GUEST_MOUNTPOINT'"

    printf -v GUEST_MOUNTPOINT_Q '%q' "$GUEST_MOUNTPOINT"
    if aivm_ssh "ls -ld -- $GUEST_MOUNTPOINT_Q >/dev/null 2>&1"; then
        echo "❌ Bad: '$AIVM_USER' can traverse or read the mounted project"
        return 1
    fi
    echo "✅ Mounted project is inaccessible to '$AIVM_USER'"

    limactl shell --workdir=/ "$LIMA_INSTANCE" \
        systemctl is-enabled --quiet aivm-appendwatch.service \
        || { echo "❌ Appendwatch service is not enabled"; return 1; }
    limactl shell --workdir=/ "$LIMA_INSTANCE" \
        systemctl is-active --quiet aivm-appendwatch.service \
        || { echo "❌ Appendwatch service is not active"; return 1; }
    printf -v GUEST_CONTROL_DIR_Q '%q' "$GUEST_CONTROL_DIR"
    printf -v GUEST_APPENDWATCH_SCRIPT_Q '%q' "$GUEST_APPENDWATCH_SCRIPT"
    printf -v GUEST_APPENDWATCH_REPORT_Q '%q' "$GUEST_APPENDWATCH_REPORT"
    limactl shell --workdir=/ "$LIMA_INSTANCE" \
        sudo -n sh -c "test -r $GUEST_APPENDWATCH_SCRIPT_Q \
            && test -s $GUEST_APPENDWATCH_REPORT_Q \
            && test \"\$(stat -c %a $GUEST_CONTROL_DIR_Q)\" = 700 \
            && test \"\$(stat -c %a $GUEST_APPENDWATCH_SCRIPT_Q)\" = 600 \
            && test \"\$(stat -c %a $GUEST_APPENDWATCH_REPORT_Q)\" = 600 \
            && test \"\$(cat $GUEST_APPENDWATCH_REPORT_Q)\" = ." \
        || { echo "❌ Appendwatch source or report is unavailable to root"; return 1; }
    [ -r "$HOST_APPENDWATCH_REPORT" ] \
        && [ "$(cat "$HOST_APPENDWATCH_REPORT")" = . ] \
        || { echo "❌ Appendwatch report is unavailable on the host"; return 1; }
    if limactl shell --workdir=/ "$LIMA_INSTANCE" \
        sudo -n find "$GUEST_CONTROL_DIR" -type f \
            \( -name '*.pyc' -o -name '*.pyo' \) -print -quit |
        grep -q .; then
        echo "❌ Appendwatch created readable bytecode"
        return 1
    fi
    local protected_probe
    local -a protected_probes=(
        "cd -- $GUEST_CONTROL_DIR_Q"
        "ls -la -- $GUEST_CONTROL_DIR_Q"
        "stat -- $GUEST_CONTROL_DIR_Q"
        "stat -- $GUEST_APPENDWATCH_SCRIPT_Q"
        "stat -- $GUEST_APPENDWATCH_REPORT_Q"
        "cat -- $GUEST_APPENDWATCH_SCRIPT_Q"
        "cat -- $GUEST_APPENDWATCH_REPORT_Q"
        "cp -- $GUEST_APPENDWATCH_SCRIPT_Q /dev/null"
        "cp -- $GUEST_APPENDWATCH_REPORT_Q /dev/null"
        "/usr/bin/python3 -B $GUEST_APPENDWATCH_SCRIPT_Q --help"
        "find $GUEST_CONTROL_DIR_Q -print"
    )
    for protected_probe in "${protected_probes[@]}"; do
        if aivm_ssh "$protected_probe >/dev/null 2>&1"; then
            echo "❌ '$AIVM_USER' passed a protected appendwatch access probe"
            return 1
        fi
    done
    echo "✅ Appendwatch is active and inaccessible to '$AIVM_USER'"

    printf -v CODEX_CONFIG_PATH_Q '%q' "$CODEX_CONFIG_PATH"
    aivm_ssh "test -f $CODEX_CONFIG_PATH_Q" \
        || { echo "❌ Codex config missing: $CODEX_CONFIG_PATH"; return 1; }
    echo "✅ Codex config exists at '$CODEX_CONFIG_PATH'"

    printf -v VSCODE_BIN_PATH_Q '%q' "$VSCODE_BIN_PATH"
    ACTUAL_VSCODE_VERSION="$(
        aivm_ssh "$VSCODE_BIN_PATH_Q --version | head -1"
    )"
    [ "$ACTUAL_VSCODE_VERSION" = "$VSCODE_VERSION" ] \
        || { echo "❌ VS Code $VSCODE_VERSION not found"; return 1; }
    echo "✅ VS Code $VSCODE_VERSION installed"

    printf -v VSCE_PATH_Q '%q' "$VSCE_PATH"
    aivm_ssh \
        "$VSCODE_BIN_PATH_Q \
        --extensions-dir $VSCE_PATH_Q \
        --list-extensions --show-versions" |
        grep -qx "$CODEX_VSCE" \
        || { echo "❌ VS Code extension $CODEX_VSCE not found"; return 1; }
    echo "✅ VS Code extension $CODEX_VSCE installed"

    printf -v CODEX_CLI_BIN_PATH_Q '%q' "$CODEX_CLI_BIN_PATH"
    ACTUAL_CODEX_CLI_VERSION="$(
        aivm_ssh "$CODEX_CLI_BIN_PATH_Q --version"
    )"
    [ "$ACTUAL_CODEX_CLI_VERSION" = "codex-cli $CODEX_CLI_VERSION" ] \
        || { echo "❌ Codex CLI $CODEX_CLI_VERSION not found"; return 1; }
    echo "✅ Codex CLI $CODEX_CLI_VERSION installed"
}

# If verified, open shell in the AIVM user's home directory
if verify_instance; then
    exec "${AIVM_SSH_CMD[@]}" \
        -t \
        "$AIVM_SSH_TARGET"
fi
