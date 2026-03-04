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
        print("❌ Error: requirements.txt not found.")
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
            print(f"⚠️  Please edit {config_path} with your API keys.")
        else:
            print("❌ Error: Config files missing.")
            return False
    return True

def launch():
    print("\n--- 🏁 Launching Intraday Bot ---")
    python_exe = sys.executable
    root_dir = os.getcwd()
    env = os.environ.copy()

    # Critical: Use -m to run as a module so that sibling/parent imports work correctly.
    # We must ensure the project root is in PYTHONPATH.
    env["PYTHONPATH"] = root_dir + os.pathsep + env.get("PYTHONPATH", "")

    try:
        # Launch using the module flag -m. This is the only way to run code
        # that uses relative imports within its own package hierarchy.
        cmd = [python_exe, "-m", "src.intraday_bot"]
        print(f"DEBUG: Command: {' '.join(cmd)}")
        subprocess.run(cmd, env=env, check=True)
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
            if "YOUR_ALPACA_API_KEY" in f.read():
                print("\n🛑 SETUP REQUIRED: Please open config/config.json and enter your real API keys.")
                input("\nPress Enter to close...")
                sys.exit(0)
        launch()
        input("\nPress Enter to close...")
