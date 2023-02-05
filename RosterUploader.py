# COPIED FROM WillowRosterUploader.py

from __future__ import print_function

import datetime
import os
import ShiftRetriever

import tkinter as tk
from tkinter import filedialog

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

CALENDAR_ID = "0ni1o3c39sd0r0boommkg87kkg@group.calendar.google.com"
DUMMY_SUMMARY = 'Dummy Event'

num_repeats = 0
MAX_REPEATS = 2


def delete_stored_tokens():
    if os.path.exists('token.json'):
        os.remove('token.json')


def get_credentials():
    global num_repeats

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    try:
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
    except Exception as error:
        if num_repeats < MAX_REPEATS:
            delete_stored_tokens()
            num_repeats += 1
            main()
        else:
            raise error
    return creds


def insert_dummy(service, now):
    global num_repeats
    now_text = now.isoformat() + 'Z'  # 'Z' indicates UTC time
    then = now + datetime.timedelta(hours=1)
    then_text = then.isoformat() + 'Z'

    # Insert dummy event
    dummy_event = {
        'summary': DUMMY_SUMMARY,
        'start': {
            'dateTime': now_text,
            'timeZone': 'Australia/Brisbane',
        },
        'end': {
            'dateTime': then_text,
            'timeZone': 'Australia/Brisbane',
        },
    }
    try:
        service.events().insert(calendarId=CALENDAR_ID, body=dummy_event).execute()
    except Exception as error:
        if num_repeats < MAX_REPEATS:
            delete_stored_tokens()
            num_repeats += 1
            main()
        else:
            raise error


def delete_dummy(service, events):
    # Delete dummy event
    for event in events:
        if event['summary'] == DUMMY_SUMMARY:
            service.events().delete(calendarId=CALENDAR_ID, eventId=event['id']).execute()
            events.remove(event)
            return
    raise RuntimeError("Couldn't delete Dummy event")


def get_filepath():
    # prompt user for file path
    root = tk.Tk()
    root.iconify()
    file_path = filedialog.askopenfilename()
    root.destroy()
    return file_path


def delete_old_shifts(service, events, shifts):
    shift_id = ShiftRetriever.SHIFT_ID

    # delete all shifts that we're about to add
    num_deleted = 0
    if not events:
        raise RuntimeError('No upcoming events found.')
    else:
        for event in events:
            if event['summary'] == shift_id:
                # if the event in the list of shifts that we need to add?
                for shift in shifts:
                    start_string = shift['start'].isoformat() + "+10:00"

                    if event['start']['dateTime'] == start_string:
                        service.events().delete(calendarId=CALENDAR_ID, eventId=event['id']).execute()
                        print("Deleting shift:", "Start:", event['start'], "End:", event['end'], "Desc:",
                              event['description'])
                        num_deleted += 1
                        break
        return num_deleted


def add_new_shifts(service, shifts, now):
    shift_id = ShiftRetriever.SHIFT_ID

    # add all shifts
    num_added = 0
    for shift in shifts:
        if shift['start'] > now:
            event = {
                'summary': shift_id,
                'start': {
                    'dateTime': shift['start'].isoformat(),
                    'timeZone': "Australia/Brisbane"
                },
                'end': {
                    'dateTime': shift['end'].isoformat(),
                    'timeZone': "Australia/Brisbane"
                },
                'description': shift['position']
            }
            service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print("Shift inserted:", shift)
            num_added += 1
    return num_added


def main():
    creds = get_credentials()

    try:
        service = build('calendar', 'v3', credentials=creds)

        now = datetime.datetime.now()
        now_text = now.isoformat() + 'Z'  # 'Z' indicates UTC time

        insert_dummy(service, now)
        print("Dummy event inserted")

        events_result = service.events().list(calendarId=CALENDAR_ID, timeMin=now_text,
                                              maxResults=70, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        delete_dummy(service, events)
        print("Dummy event deleted")

        file_path = get_filepath()

        shifts = ShiftRetriever.retrieve_shifts_from_pdf(file_path)

        num_deleted = delete_old_shifts(service, events, shifts)

        num_added = add_new_shifts(service, shifts, now)

        print("Finished adding shifts.\nShifts added:", num_added, "\nShifts deleted:", num_deleted)

    except HttpError as error:
        print('An error occurred: %s' % error)


if __name__ == '__main__':
    main()
