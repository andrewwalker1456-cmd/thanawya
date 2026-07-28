import os, sys, subprocess, time, signal, logging

def main():
    os.chdir("/home/z/my-project/thanaweya_bot")
    env = os.environ.copy()
    # Don't set SOURCE_FILE — let it use upload dir where cache works
    env["BOT_TOKEN"] = "8769493338:AAFA5UCWY_N4UvciWdtle8l7bD911AdRbLU"
    env["ADMIN_IDS"] = "373303307"
    env["LOG_LEVEL"] = "INFO"
    env["PYTHONUNBUFFERED"] = "1"

    log_file = open("/home/z/my-project/thanaweya_bot/bot_output.log", "a")

    while True:
        log_file.write(f"\n--- Restarting bot at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_file.flush()

        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "bot.main"],
            env=env,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        proc.wait()
        log_file.write(f"--- Bot exited with code {proc.returncode} at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_file.flush()
        time.sleep(2)  # restart delay

if __name__ == "__main__":
    main()