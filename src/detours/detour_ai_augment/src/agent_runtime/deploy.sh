#!/bin/bash
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
user:
  name: "$AIVM_USER"
  home: "$AIVM_HOME"
EOF
}
# Codex config to ship with AIVM
AIVM_CODEX_CONFIG_PATH="$AIVM_HOME/.codex/config.toml"
build_aivm_provision() {
    cat <<EOF
  - mode: user
    script: |
      mkdir -p "$AIVM_HOME/.codex"
      chmod 700 "$AIVM_HOME/.codex"
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
      chmod 600 "$AIVM_HOME/.codex/config.toml"
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
    
    # Create a minimal Lima template for Apple Silicon
    cat > /tmp/aicode.yaml <<EOF
# Minimal aicode configuration for Apple Silicon
images:
  - location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
    arch: "aarch64"

${AIVM_CONFIG:-}

# ONLY mount the project directory - no defaults
mounts:
  - location: "$MOUNT_DIR"
    mountPoint: "$GUEST_WORKDIR"
    writable: true

mountType: "reverse-sshfs"

cpus: 4
memory: "4GiB"
disk: "10GiB"

# Ensure mount point exists
provision:
  - mode: system
    script: |
      mkdir -p "$GUEST_WORKDIR"
${AIVM_PROVISION:-}
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

    if [ "$AIVM_MODE" -eq 1 ]; then
        limactl shell --workdir=/ "$LIMA_INSTANCE" \
            test -f "$AIVM_CODEX_CONFIG_PATH" \
            || { echo "❌ Codex config missing: $AIVM_HOME/.codex/config.toml"; return 1; }
        echo "✅ Codex config exists at '$AIVM_CODEX_CONFIG_PATH'"
    fi
}

# If verified, open shell in project directory
verify_instance && exec limactl shell --workdir="$GUEST_WORKDIR" "$LIMA_INSTANCE" bash
