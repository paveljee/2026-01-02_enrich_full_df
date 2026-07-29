#!/bin/bash

# NOTE: this is deprecated and will not be used.
# The reason is because these changes ultimately
# did not help solve the issue of enforcing
# append-only Codex sessions.
#
# Logging for historical purposes; will roll back.

set -e

SCRIPT_NAME="aicode"
INSTALL_PATH="$HOME/.local/bin/$SCRIPT_NAME"
PROJECT_DIR="/Volumes/home/aicode"
LIMA_INSTANCE="aicode"
MOUNT_DIR="$PROJECT_DIR"
# Though using the real --mount dir downstream to preserve macOS paths
DEFAULT_MOUNTPOINT="$PROJECT_DIR"
GUEST_WORKDIR="$DEFAULT_MOUNTPOINT"

### BEGIN AIVM-SPECIFIC CONFIGS ###
# AIVM if fresh instance needed
AIVM_LIMA_INSTANCE="aivm"
AIVM_MODE=0
AIVM_USER="myvm"
AIVM_HOME="/home/$AIVM_USER"
AIVM_GUEST_WORKDIR="$AIVM_HOME/workdir"
# Lima config to be injected in AIVM
build_aivm_config() {
    cat <<EOF
#plain: true

user:
  name: "$AIVM_USER"
  home: "$AIVM_HOME"
#  passwordlessSudo: false

#mounts: []
EOF
}
# Codex etc. config to ship with AIVM
VSCODE_VERSION="1.130.0"
VSCODE_COMMIT="1b6a188127eeaf9194f945eb6eb89a657e93c54c"
VSCODE_URL="https://update.code.visualstudio.com/commit:$VSCODE_COMMIT/server-linux-arm64/stable"
VSCODE_PATH="$AIVM_HOME/.vscode-server/bin/$VSCODE_COMMIT"
VSCODE_BIN_PATH="$VSCODE_PATH/bin/code-server"
VSCE_PATH="$AIVM_HOME/.vscode-server/extensions"
CODEX_VSCE_VERSION="26.721.41059"
CODEX_VSCE="openai.chatgpt@$CODEX_VSCE_VERSION"
#CODEX_PATH="$AIVM_HOME/.codex"
CODEX_PATH="$AIVM_HOME/workdir/.codex"
CODEX_CONFIG_PATH="$CODEX_PATH/config.toml"
build_aivm_provision() {
    cat <<EOF
#provision:
  #- mode: user
  #  script: |
  #    mkdir -p "$GUEST_WORKDIR"
  - mode: user
    script: |
      mkdir -p "$CODEX_PATH"
      chmod 700 "$CODEX_PATH"
      cat > "$CODEX_CONFIG_PATH" <<'CODEX_CONFIG'
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
      chmod 600 "$CODEX_CONFIG_PATH"
  - mode: user
    script: |
      mkdir -p "$VSCODE_PATH"
      curl -fsSL "$VSCODE_URL" |
        tar -xz --strip-components=1 -C "$VSCODE_PATH"
      "$VSCODE_BIN_PATH" \
        --extensions-dir "$VSCE_PATH" \
        --install-extension "$CODEX_VSCE" --force
  - mode: user
    script: |
      line='export CODEX_HOME="$CODEX_PATH"'
      for file in "$AIVM_HOME/.profile" "$AIVM_HOME/.bashrc"; do
        touch "\$file"
        grep -qxF "\$line" "\$file" || printf '\n%s\n' "\$line" >> "\$file"
      done
EOF
}
### END AIVM-SPECIFIC CONFIGS ###

# Self-install function
self_install() {
    if [ "$0" != "$INSTALL_PATH" ]; then
        echo "📦 Installing $SCRIPT_NAME to $INSTALL_PATH..."
        mkdir -p "$HOME/.local/bin"
        cp "$0" "$INSTALL_PATH"
        chmod +x "$INSTALL_PATH"
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
            GUEST_WORKDIR="$MOUNT_DIR"
            shift 2
            ;;
        --aivm)
            AIVM_MODE=1
            shift
            ;;
        *)
            echo "❌ Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ "$AIVM_MODE" -eq 1 ]; then
    LIMA_INSTANCE="$AIVM_LIMA_INSTANCE"
    GUEST_WORKDIR="$AIVM_GUEST_WORKDIR"
fi

# Navigate to project directory
cd "$MOUNT_DIR" || { echo "❌ Directory not found: $MOUNT_DIR"; exit 1; }

# Always recreate the AIVM instance but prompt to be sure
if [ "$AIVM_MODE" -eq 1 ] && limactl list | grep -q "^$LIMA_INSTANCE"; then
    echo "♻️ Recreating Lima instance '$LIMA_INSTANCE'..."
    read -r -p "⚠️ Delete Lima instance '$LIMA_INSTANCE'? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS])
            limactl delete -f "$LIMA_INSTANCE"
            ;;
        *)
            echo "❌ Use existing instance with \`limactl shell $LIMA_INSTANCE\`"
            exit 0
            ;;
    esac
fi

# Update the existing instance's mount when --mount is used
if limactl list | grep -q "^$LIMA_INSTANCE"; then
    CONFIG="$HOME/.lima/$LIMA_INSTANCE/lima.yaml"

    limactl stop "$LIMA_INSTANCE" 2>/dev/null || true

    awk -v location="$MOUNT_DIR" -v mountpoint="$GUEST_WORKDIR" '
        /^mounts:/ {
            print "mounts:"
            print "  - location: \"" location "\""
            print "    mountPoint: \"" mountpoint "\""
            print "    writable: true"
            replacing=1
            next
        }
        replacing && /^[^[:space:]]/ {
            replacing=0
        }
        /^[[:space:]]*mkdir -p / {
            print "      mkdir -p \"" mountpoint "\""
            next
        }
        !replacing { print }
    ' "$CONFIG" > "$CONFIG.tmp"

    mv "$CONFIG.tmp" "$CONFIG"
fi

# Check if Lima instance exists and is running
if limactl list | grep -q "^$LIMA_INSTANCE.*Running"; then
    echo "✅ Lima instance '$LIMA_INSTANCE' is already running"
elif limactl list | grep -q "^$LIMA_INSTANCE"; then
    echo "🔄 Lima instance '$LIMA_INSTANCE' exists but not running, starting..."
    limactl start "$LIMA_INSTANCE"
else
    echo "🚀 Creating new Lima instance '$LIMA_INSTANCE'..."

    if [ "$AIVM_MODE" -eq 1 ]; then
        AIVM_CONFIG="$(build_aivm_config)"
        AIVM_PROVISION="$(build_aivm_provision)"
    fi

    AICODE_MOUNTS="$(cat <<EOF
# ONLY mount the project directory - no defaults
mounts:
  - location: "$MOUNT_DIR"
    mountPoint: "$GUEST_WORKDIR"
    writable: true

mountType: "reverse-sshfs"
EOF
)"

    AICODE_PROVISION="$(cat <<EOF
# Ensure mount point exists
#provision:
  - mode: system
    script: |
      mkdir -p "$GUEST_WORKDIR"
EOF
)"
    
    # Create a minimal Lima template for Apple Silicon
    cat > /tmp/aicode.yaml <<EOF
# Minimal aicode configuration for Apple Silicon
images:
  - location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
    arch: "aarch64"

${AIVM_CONFIG:-}

$AICODE_MOUNTS

cpus: 4
memory: "4GiB"
disk: "10GiB"

provision:
${AIVM_PROVISION:-}

$AICODE_PROVISION
EOF

    # Start with the minimal template
    # No need to prompt if AIVM because already prompted to delete above
    limactl start \
        $([ "$AIVM_MODE" -eq 1 ] && echo --yes) \
        --name="$LIMA_INSTANCE" \
        /tmp/aicode.yaml
    
    echo "✅ Lima instance created successfully"
fi

verify_instance() {
    LIMA_SSH_CONFIG_PATH="$HOME/.lima/$LIMA_INSTANCE/ssh.config"
    ssh -F "$LIMA_SSH_CONFIG_PATH" "lima-$LIMA_INSTANCE" \
        true \
        || { echo "❌ SSH access failed"; return 1; }
    echo "✅ SSH access from host works"

    limactl shell --workdir=/ "$LIMA_INSTANCE" \
        test -w "$GUEST_WORKDIR" \
        || { echo "❌ Workdir is not writable: $GUEST_WORKDIR"; return 1; }
    echo "✅ Workdir is writable at '$GUEST_WORKDIR'"

    PROBE=".aicode-probe-$$"
    limactl shell --workdir=/ "$LIMA_INSTANCE" \
        touch "$GUEST_WORKDIR/$PROBE"
    if [ -f "$MOUNT_DIR/$PROBE" ]; then
        rm -f "$MOUNT_DIR/$PROBE"
        if [ "$AIVM_MODE" -eq 0 ]; then
            echo "✅ Workdir is mounted"
        else
            echo "❌ Bad: workdir is mounted"
            return 1
        fi
    else
        limactl shell --workdir=/ "$LIMA_INSTANCE" \
            rm -f "$GUEST_WORKDIR/$PROBE"
        if [ "$AIVM_MODE" -eq 0 ]; then
            echo "❌ Bad: workdir is not mounted"
            return 1
        else
            echo "✅ Workdir is not mounted"
        fi
    fi

    if [ "$AIVM_MODE" -eq 1 ]; then
        limactl shell --workdir=/ "$LIMA_INSTANCE" \
            test -f "$CODEX_CONFIG_PATH" \
            || { echo "❌ Codex config missing: $CODEX_CONFIG_PATH"; return 1; }
        echo "✅ Codex config exists at '$CODEX_CONFIG_PATH'"

        limactl shell --workdir=/ "$LIMA_INSTANCE" \
            sh -c 'test "$("$1" --version | head -1)" = "$2"' \
                sh "$VSCODE_BIN_PATH" "$VSCODE_VERSION" \
            || { echo "❌ VS Code $VSCODE_VERSION not found"; return 1; }
        echo "✅ VS Code $VSCODE_VERSION installed"

        limactl shell --workdir=/ "$LIMA_INSTANCE" \
            "$VSCODE_BIN_PATH" \
            --extensions-dir "$VSCE_PATH" \
            --list-extensions --show-versions |
            grep -qx "$CODEX_VSCE" \
            || { echo "❌ VS Code extension $CODEX_VSCE not found"; return 1; }
        echo "✅ VS Code extension $CODEX_VSCE installed"
    fi
}

# If verified, open shell in project directory
verify_instance && \
    exec limactl shell --workdir="$GUEST_WORKDIR" "$LIMA_INSTANCE" bash
