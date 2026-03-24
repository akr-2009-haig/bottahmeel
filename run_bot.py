import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

if len(sys.argv) > 1 and sys.argv[1].strip().lower() == "worker":
    os.environ["BOT_MODE"] = "worker"

from bot.main import main

if __name__ == "__main__":
    main()
