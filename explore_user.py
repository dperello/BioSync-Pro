import fitparse

file_path = "/Users/user/Artsessions/python/Drift/example fit/21687154187_ACTIVITY.fit"
fit_file = fitparse.FitFile(file_path)

print("--- User Profile Messages ---")
for profile in fit_file.get_messages('user_profile'):
    print(profile.get_values())

print("\n--- Session Messages (for calories) ---")
for session in fit_file.get_messages('session'):
    vals = session.get_values()
    print({k: vals[k] for k in ['total_calories', 'avg_heart_rate', 'total_timer_time'] if k in vals})
