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

    # Set PYTHONPATH to current working directory (project root)
    env = os.environ.copy()
    root_dir = os.getcwd()
    env["PYTHONPATH"] = root_dir + os.pathsep + env.get("PYTHONPATH", "")

    print(f"DEBUG: Project Root: {root_dir}")
    print(f"DEBUG: Python: {python_exe}")

    # Run as a module to handle imports correctly
    try:
        # Use -m and explicitly set PYTHONPATH
        subprocess.run([python_exe, "-m", "src.intraday_bot"], env=env, check=True)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error launching bot: {e}")
    except Exception as e:
        print(f"❌ Unexpected error during launch: {e}")

if __name__ == "__main__":
    # Ensure we are in the root directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    if not os.path.exists("src") or not os.path.exists("config"):
        print(f"❌ Error: Please run this script from the project root directory. Currently in: {os.getcwd()}")
        sys.exit(1)

    if setup():
        # Check if user needs to fill config
        config_path = os.path.join("config", "config.json")
        with open(config_path, 'r') as f:
            content = f.read()
            if "YOUR_ALPACA_API_KEY" in content:
                print("\n🛑 SETUP REQUIRED: Please open config/config.json and enter your real API keys.")
                sys.exit(0)

        try:
            launch()
        except Exception as e:
            print(f"❌ Critical error: {e}")

        input("\nPress Enter to close...")
