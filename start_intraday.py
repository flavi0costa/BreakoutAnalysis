import os
import sys
import subprocess
import shutil

def run_command(command, env=None):
    print(f"Running: {command}")
    try:
        subprocess.check_call(command, shell=True, env=env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return False

def setup():
    print("--- 🚀 Intraday Bot Auto-Setup ---")
    if not os.path.exists("requirements.txt"):
        print("❌ Error: requirements.txt not found in current directory.")
        return False
    print("📦 Installing dependencies...")
    python_exe = sys.executable
    if not run_command(f'"{python_exe}" -m pip install -r requirements.txt'):
        return False
    print("🎭 Installing Playwright browsers...")
    run_command(f'"{python_exe}" -m playwright install chromium')
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
    root_dir = os.getcwd()
    env = os.environ.copy()
    env["PYTHONPATH"] = root_dir + os.pathsep + env.get("PYTHONPATH", "")

    # We try both direct execution and module-style for maximum compatibility
    bot_script = os.path.join("src", "intraday_bot.py")

    try:
        print(f"DEBUG: Project Root: {root_dir}")
        print(f"DEBUG: PYTHONPATH: {env['PYTHONPATH']}")
        subprocess.run([python_exe, bot_script], env=env, check=True)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user.")
    except Exception as e:
        print(f"❌ Error launching bot: {e}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir:
        os.chdir(base_dir)
    if setup():
        config_path = os.path.join("config", "config.json")
        with open(config_path, 'r') as f:
            content = f.read()
            if "YOUR_ALPACA_API_KEY" in content:
                print("\n🛑 SETUP REQUIRED: Please open config/config.json and enter your real API keys.")
                input("\nPress Enter to close...")
                sys.exit(0)
        launch()
        input("\nPress Enter to close...")
