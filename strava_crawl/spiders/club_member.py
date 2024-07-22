import os
import scrapy
import re
import csv

from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from dataclasses import dataclass, field

@dataclass
class Athlete:
    athlete_id: str
    name: str
    avatar_src: str
    records: dict = field(default_factory=dict)

def convert_to_seconds(time_str):
    if 's' in time_str:
        return int(time_str.replace('s', ''))
    parts = time_str.split(':')
    if len(parts) == 2:  # mm:ss
        minutes, seconds = parts
        return int(minutes) * 60 + int(seconds)
    elif len(parts) == 3:  # hh:mm:ss
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return 0



class StravaSpider(scrapy.Spider):
    name = 'club_member'
    allowed_domains = ['strava.com']
    club_id = os.getenv('STRAVA_CLUB_ID')
    page = 1
    start_urls = [f'https://www.strava.com/clubs/1140105/members?page={i}&page_uses_modern_javascript=true' for i in range(1, 10)]
    target_titles = ["400m", "1/2 mile", "1K", "1 mile", "2 mile", "5K", "10K", "15K", "10 mile", "20K", "Half-Marathon", "Marathon"]

    def __init__(self, *args, **kwargs):
        super(StravaSpider, self).__init__(*args, **kwargs)
        self.athletes_data = []

    def start_requests(self):
        # Get the cookie from the environment
        strava_cookie = os.getenv('STRAVA_COOKIE')

        if not strava_cookie:
            self.logger.error('No STRAVA_COOKIE found in environment variables')
            return

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Priority': 'u=0, i',
            'Referer': 'https://www.strava.com/clubs/1140105/members?page=2&page_uses_modern_javascript=true',
            'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }

        cookies = {}
        for cookie in strava_cookie.split('; '):
            key, value = cookie.split('=', 1)
            cookies[key] = value

        for url in self.start_urls:
                yield scrapy.Request(url,headers=headers, cookies=cookies, callback=self.parse,)

    def parse(self, response):
        soup = BeautifulSoup(response.text, 'html.parser')
        athlete_links = soup.find_all('a', href=re.compile(r'^/athletes/'))

        for a_tag in athlete_links:
                href = a_tag['href']
                text = a_tag.get_text(strip=True)
                athlete_url = response.urljoin(a_tag['href'])
                print(f'Link: {href}, Text: {text}')
                yield scrapy.Request(athlete_url, callback=self.parse_athlete, headers=response.request.headers, cookies=response.request.cookies)

    def parse_athlete(self, response):
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract the athlete's ID from the URL
        athlete_id = re.search(r'/athletes/(\d+)', response.url).group(1)
        # Extract the athlete's name
        name_tag = soup.find('h1', class_='text-title1 athlete-name')
        name = name_tag.get_text(strip=True) if name_tag else 'N/A'
        # Extract the avatar image src that contains the athlete's ID
        avatar_src = 'N/A'
        avatar_tags = soup.find_all('img', class_='avatar-img')
        for avatar_tag in avatar_tags:
            if athlete_id in avatar_tag['src']:
                avatar_src = avatar_tag['src']
                break

        # Create an Athlete instance
        athlete = Athlete(athlete_id=athlete_id, name=name, avatar_src=avatar_src)


        # Make an additional request to the profile sidebar comparison URL
        profile_comparison_url = f'https://www.strava.com/athletes/{athlete_id}/profile_sidebar_comparison?hl=en-US'

        profile_comparison_headers = {
            'Accept': 'text/javascript, application/javascript, application/ecmascript, application/x-ecmascript',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            'Priority': 'u=1, i',
            'Referer': f'https://www.strava.com/athletes/{athlete_id}',
            'Sec-Ch-Ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'X-Csrf-Token': 'CiGWauewyqfEpwNlqUcWwkCRc3tqkPmydrpWIxw05oyBmQ_CklB0QYceGyOr9ZqcdK5SqcsO_GJ3qN_V9oNhnQ',
            'X-Requested-With': 'XMLHttpRequest'
        }

        yield scrapy.Request(profile_comparison_url, callback=self.parse_profile_comparison, headers=profile_comparison_headers, cookies=response.request.cookies, meta={'athlete': athlete})

    def parse_profile_comparison(self, response):
        # Extract additional information from the profile sidebar comparison page
        athlete = response.meta['athlete']

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the tbody with id=all-time-prs
        all_time_prs_tbody = soup.find('tbody', id='all-time-prs')
        next_tbody = all_time_prs_tbody.find_next('tbody') if all_time_prs_tbody else None
        if next_tbody:
            # List all tr tags inside this tbody, skip the first one
            tr_tags = next_tbody.find_all('tr')[1:]

            for tr in tr_tags:
                # Get the title from the first td tag
                title_td = tr.find('td')
                title = title_td.get_text(strip=True) if title_td else 'N/A'

                # Get the record from the second td tag
                record_td = title_td.find_next('td') if title_td else None
                record = record_td.get_text(strip=True) if record_td else 'N/A'

                # Store the record if the title is in the target titles
                if title in self.target_titles:
                    athlete.records[title] = convert_to_seconds(record)

        # Print or store the athlete information
        print(f'Athlete ID: {athlete.athlete_id}, Name: {athlete.name}, Avatar: {athlete.avatar_src}, Records: {athlete.records}')
        # Append the athlete data to the list
        self.athletes_data.append({
            'athlete_id': athlete.athlete_id,
            'name': athlete.name,
            'avatar_src': athlete.avatar_src,
            'records': athlete.records
        })

    def close(self, reason):
        # Define the CSV file columns
        fieldnames = ['athlete_id', 'name', 'avatar_src'] + self.target_titles

        # Write the data to a CSV file
        with open('athletes_data.csv', 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for athlete in self.athletes_data:
                row = {
                    'athlete_id': athlete['athlete_id'],
                    'name': athlete['name'],
                    'avatar_src': athlete['avatar_src']
                }
                row.update(athlete['records'])
                writer.writerow(row)
