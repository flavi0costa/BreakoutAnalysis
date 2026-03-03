import os
import sys
import subprocess
import shutil

def run_command(command):
    print(f"Running: {command}")
    try:
        subprocess.check_call(command, shell=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return False

def setup():
    print("--- 🚀 Intraday Bot Auto-Setup ---")

    # 1. Check for requirements.txt
    if not os.path.exists("requirements.txt"):
        print("❌ Error: requirements.txt not found in current directory.")
        return False

    # 2. Install dependencies
    print("📦 Installing dependencies...")
    python_exe = sys.executable
    if not run_command(f'"{python_exe}" -m pip install -r requirements.txt'):
        return False

    # 3. Playwright install
    print("🎭 Installing Playwright browsers...")
    run_command(f'"{python_exe}" -m playwright install chromium')

    # 4. Config check
    config_path = os.path.join("config", "config.json")
    example_path = os.path.join("config", "config.example.json")

    if not os.path.exists(config_path):
        if os.path.exists(example_path):
            print(f"📝 Creating {config_path} from example...")
            shutil.copy(example_path, config_path)
            print(f"⚠️  Please edit {config_path} with your API keys before running again.")
        else:
            print("❌ Error: Config files missing in config/ directory.")
            return False
    else:
        print("✅ config.json found.")

    return True

def launch():
    print("\n--- 🏁 Launching Intraday Bot ---")
    python_exe = sys.executable

    # Set PYTHONPATH to project root
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

    bot_path = os.path.join("src", "intraday_bot.py")

    try:
        subprocess.run([python_exe, bot_path], env=env, check=True)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user.")
    except Exception as e:
        print(f"❌ Error launching bot: {e}")

if __name__ == "__main__":
    # Ensure we are in the root directory
    if not os.path.exists("src") or not os.path.exists("config"):
        print("❌ Error: Please run this script from the project root directory.")
        sys.exit(1)

    if setup():
        # Check if user wants to run now
        # For an auto-script, we can just try to run it.
        # But if we just created the config, they might need to edit it first.
        config_path = os.path.join("config", "config.json")
        with open(config_path, 'r') as f:
            content = f.read()
            if "YOUR_ALPACA_API_KEY" in content:
                print("\n🛑 SETUP REQUIRED: Please open config/config.json and enter your real API keys.")
                sys.exit(0)

        launch()
