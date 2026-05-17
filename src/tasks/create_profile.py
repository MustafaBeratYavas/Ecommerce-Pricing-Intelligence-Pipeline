"""Create the persistent Chrome profile directory used by scraper runs."""

import argparse
import os
import sys

if __name__ == "__main__" and __package__ is None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, root_dir)

from src.core.config import Config


def create_chrome_profile(user_data_dir: str, profile_name: str):
    # Resolve profile paths relative to the repository root.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(current_dir))

    full_user_data_path = os.path.join(root_dir, user_data_dir)
    full_profile_path = os.path.join(full_user_data_path, profile_name)

    print(f"User Data Path: {full_user_data_path}")
    print(f"Profile Name:   {profile_name}")

    # Create the profile directory tree idempotently.
    if not os.path.exists(full_profile_path):
        try:
            os.makedirs(full_profile_path, exist_ok=True)
            print(f"Successfully created profile directory: {full_profile_path}")
        except OSError as e:
            print(f"Error creating profile directory: {e}")
            sys.exit(1)
    else:
        print("Profile directory already exists.")


def main():
    # Parse CLI arguments and initialize the profile directory.
    config = Config()
    parser = argparse.ArgumentParser(
        description="E-Commerce Pricing Intelligence Pipeline - Chrome Profile Creator"
    )

    parser.add_argument("--user-data-dir", default=None)
    parser.add_argument("--profile-name", default=None)

    args = parser.parse_args()
    user_data_dir = args.user_data_dir or config.get(
        "browser", "user_data_dir", default=".browser_profile"
    )
    profile_name = args.profile_name or config.get(
        "browser", "profile_name", default="Profile 1"
    )
    create_chrome_profile(user_data_dir, profile_name)


if __name__ == "__main__":
    main()
