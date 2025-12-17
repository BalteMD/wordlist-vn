from datetime import datetime, timedelta
import argparse
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


def combine_wordlists(file1, file2, output_file):
    combined_list = []
    with open(file1, 'r', encoding='utf-8') as f1, \
         open(file2, 'r', encoding='utf-8') as f2:
        wordlist1 = [line.strip() for line in f1]
        wordlist2 = [line.strip() for line in f2]

    for word1 in wordlist1:
        for word2 in wordlist2:
            combined_list.append(word1 + word2)

    with open(output_file, 'w', encoding='utf-8') as f:
        for word in combined_list:
            f.write(word + '\n')

def generate_date_times(start_year: int, end_year: int, filename: str = "date_times.txt") -> None:
    """Generate all dates from 01/01/start_year to 31/12/end_year and write them to a file."""
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)

    date_times = []
    current_date = start_date

    while current_date <= end_date:
        date_times.append(current_date.strftime("%d%m%Y"))
        current_date += timedelta(days=1)

    with open(filename, "w", encoding="utf-8") as file:
        for dt in date_times:
            file.write(dt + "\n")


def _crawl_single_user(session: requests.Session, base_url: str, user_id: int, cookies: dict, headers: dict) -> tuple[int, str]:
    """Crawl a single user and return (user_id, username)."""
    url = f"{base_url}.{user_id}/"
    username = "N/A"
    try:
        response = session.get(url, headers=headers, cookies=cookies, allow_redirects=False, timeout=10)
        response.raise_for_status()
        location_url = response.headers.get("Location")
        if location_url:
            # Extract username from the Location header safely
            try:
                parts = location_url.rstrip("/").split("/")
                last_segment = parts[-1] or parts[-2]
                username = last_segment.split(".")[0]
            except (IndexError, ValueError):
                # If parsing fails for this id, skip it but continue crawling
                username = "N/A"
    except requests.exceptions.RequestException:
        pass
    
    return (user_id, username)


def get_user_locations(base_url: str, user_id_range, filename: str, max_workers: int = 20) -> None:
    """Crawl usernames from voz for the given ID range and write them to a file.
    
    Args:
        base_url: Base URL to crawl
        user_id_range: Range of user IDs to crawl
        filename: Output filename
        max_workers: Number of concurrent threads (default: 20)
    """
    burp0_cookies = {"cf_clearance": "xThufzN_LUmWzJIyFrLS43cQ3_451rlOkA34OWtGwjc-1765973011-1.2.1.1-pGyvuO_xIoET2I6yskHz7U5fu1eZycEZokjN_hQN3a3KyeDRW7o4RC2diU0Tze2wfM7TmciTUkplarrpIz1pGUzPajCtmOViaIcwNUbT.m3OhfWvCl6Dksjwp2MDoK9xRK37Ms21rEcUb2VLEqldYYwHpoo6J4YQuCWkrXB5XblRTj8c.2dy1LXNAVGhWaznmxnWTUUBALEJ.X_sk7QvslZS08b6F6y1mOnNCJLxBJBo7zjnfa3jsnE5WbNP8iq9"}
    burp0_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"}
    
    # Use Session for connection pooling
    session = requests.Session()
    file_lock = Lock()
    
    # Open file in write mode to start fresh, then switch to append mode
    with open(filename, "w", encoding="utf-8") as outfile:
        pass  # Create/clear the file
    
    # Process user IDs concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_user_id = {
            executor.submit(_crawl_single_user, session, base_url, user_id, burp0_cookies, burp0_headers): user_id
            for user_id in user_id_range
        }
        
        # Write results to file as they complete
        for future in as_completed(future_to_user_id):
            user_id, username = future.result()
            print(f"Crawled id: {user_id}, User: {username}")  # progress log
            
            # Write to file immediately with thread-safe lock
            with file_lock:
                with open(filename, "a", encoding="utf-8") as outfile:
                    if username != "N/A":
                        outfile.write(f"{username}\n")
                    else:
                        outfile.write("\n")
    
    session.close()


def filter_passwords(input_file: str, output_file: str, pattern_type: str = "default", custom_pattern: str = None) -> None:
    """Filter passwords from input file based on regex pattern and write to output file."""
    # Define available patterns
    patterns = {
        "voz_username": "https\://voz\.vn/u/(.*?)\.",
        "all_four": "^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[\\`~!@#$%^&*()_+\/*\-=.\[\]\{\}\":;\'?,<>]).{8,16}$",
        "three_conditions": "^(?![a-zA-Z]+$)(?![A-Z0-9]+$)(?![A-Z\\W_]+$)(?![a-z0-9]+$)(?![a-z\\W_]+$)(?![0-9\\W_]+$)[a-zA-Z0-9\\W_]{6,16}$",
        "letter_digit_special": "^(?=.*[A-Za-z])(?=.*\d)(?=.*[\\`~!@#$%^&*()_+\/*\-=.\[\]\{\}\":;\'?,<>])[A-Za-z\d\\`~!@#$%^&*()_+\/*\-=.\[\]\{\}\":;\'?,<>]{6,16}$",
        "upper_lower_digit": "(?![0-9A-Z]+$)(?![0-9a-z]+$)(?![a-zA-Z]+$)[0-9A-Za-z]{8,20}$",
        "digit_and_letter": "^(?![0-9]+$)(?![a-zA-Z]+$)[0-9A-Za-z]{8,16}$",
        "default": "^(?=.*[A-Z])(?=.*[0-9])(?=.*[a-z])(?!.*([\\`~!@#$%^&*()_+\/*\-=.\[\]\{\}\":;\'?,<>]).*\\1.*\\1)[A-Z0-9a-z\\`~!@#$%^&*()_+\/*\-=.\[\]\{\}\":;\'?,<>]{8,16}$"
    }
    
    # Select pattern
    if custom_pattern:
        patten = custom_pattern
    elif pattern_type in patterns:
        patten = patterns[pattern_type]
    else:
        patten = patterns["default"]
    
    count = 0
    ok_count = 0
    passlist = []
    
    # Read passwords from input file
    with open(input_file, 'r', encoding='UTF-8') as password:
        for count, line in enumerate(password):
            passlist.append(line)
    count += 1
    print(f"Read {count} passwords in total")
    
    # Filter passwords and write to output file
    with open(output_file, 'a+', encoding='UTF-8') as pass_ok:
        for pwd in passlist:
            pwd = pwd.strip("\n")
            try:
                re_ok = re.search(patten, pwd).group(0)
                ok_count += 1
                info = re_ok + "\n"
                pass_ok.write(info)
                print(re_ok)
            except Exception:
                continue
    
    print(f"Extracted {ok_count} matching passwords from {count} total passwords")



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate date list, crawl voz usernames, or combine wordlists using command-line arguments."
    )

    parser.add_argument(
        "--mode",
        choices=["date", "crawl", "combine", "filter"],
        required=True,
        help="Select 'date' to generate dates, 'crawl' to crawl voz usernames, 'combine' to merge two wordlists, or 'filter' to filter passwords.",
    )

    # Date generation options
    parser.add_argument(
        "--start-year",
        type=int,
        default=1970,
        help="Start year for date generation (default: 1970).",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2026,
        help="End year for date generation (default: 2026).",
    )

    # Crawling options
    parser.add_argument(
        "--base-url",
        type=str,
        default="https://voz.vn/u/dummy",
        help="Base URL to crawl (default: https://voz.vn/u/dummy).",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=1,
        help="Start user ID to crawl (default: 1).",
    )
    parser.add_argument(
        "--end-id",
        type=int,
        default=1000,
        help="End user ID to crawl (inclusive, default: 1000).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=20,
        help="Number of concurrent threads for crawling (default: 20). Increase for faster crawling, but be mindful of server limits.",
    )

    # Wordlist combine options
    parser.add_argument(
        "--file1",
        type=str,
        help="First wordlist file to combine (used when mode='combine').",
    )
    parser.add_argument(
        "--file2",
        type=str,
        help="Second wordlist file to combine (used when mode='combine').",
    )

    # Password filter options
    parser.add_argument(
        "--input-file",
        type=str,
        help="Input password file to filter (used when mode='filter').",
    )
    parser.add_argument(
        "--pattern-type",
        type=str,
        choices=["all_four", "three_conditions", "letter_digit_special", "upper_lower_digit", "digit_and_letter", "voz_username", "default"],
        default="default",
        help="Pattern type for password filtering (default: 'default'). Options: all_four, three_conditions, letter_digit_special, upper_lower_digit, digit_and_letter, default",
    )
    parser.add_argument(
        "--custom-pattern",
        type=str,
        help="Custom regex pattern for password filtering (used when mode='filter'). Overrides --pattern-type.",
    )

    # Common output option
    parser.add_argument(
        "--output",
        type=str,
        help=(
            "Output filename. If not set: date_times.txt for 'date', "
            "vozer_crawler.txt for 'crawl', combined.txt for 'combine', "
            "filtered_passwords.txt for 'filter'."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.mode == "date":
        output_file = args.output or "date_times.txt"
        generate_date_times(args.start_year, args.end_year, output_file)
        print(f"Date list has been written to {output_file}")

    elif args.mode == "crawl":
        output_file = args.output or "vozer_crawler.txt"
        if args.start_id > args.end_id:
            raise ValueError("start-id must be <= end-id")

        user_id_range = range(args.start_id, args.end_id + 1)
        get_user_locations(args.base_url, user_id_range, output_file, args.max_workers)
        print(f"Crawling finished. Data saved to {output_file}")

    elif args.mode == "combine":
        if not args.file1 or not args.file2:
            raise ValueError("When mode='combine', you must provide both --file1 and --file2")

        output_file = args.output or "combined.txt"
        combine_wordlists(args.file1, args.file2, output_file)
        print(f"Combined wordlist has been written to {output_file}")

    elif args.mode == "filter":
        if not args.input_file:
            raise ValueError("When mode='filter', you must provide --input-file")

        output_file = args.output or "filtered_passwords.txt"
        filter_passwords(args.input_file, output_file, args.pattern_type, args.custom_pattern)
        print(f"Filtered passwords have been written to {output_file}")


if __name__ == "__main__":
    main()