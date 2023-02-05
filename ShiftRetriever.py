import fitz
import io
from PIL import Image
from pytesseract import pytesseract

import cv2 as cv
import numpy as np
from datetime import datetime, timedelta

SHIFT_ID = "Amy Work"
SHOW_IMAGES = False
DAYS_OF_THE_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

FILES = ["pdfs/Roster_week_beginning_Monday_6th_February_2023.pdf",
         "pdfs/Roster_week_beginning_Monday_23rd_January_2023.pdf",
         "pdfs/Roster_week_beginning_Monday_30th_January_2023.pdf"]
FILE = "pdfs/Roster_week_beginning_Monday_6th_February_2023.pdf"


def retrieve_shifts_from_pdf(file):
    # Setup pytesseract
    path_to_tesseract = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    pytesseract.tesseract_cmd = path_to_tesseract

    # open the file
    pdf_file = fitz.open(file)

    print(f"[+] Found a total of {pdf_file.page_count} pages in file")

    # list of PIL Images
    images = []

    # capture all images in pdf
    for page_index in range(len(pdf_file)):

        # get the page itself
        page = pdf_file[page_index]
        image_list = page.get_images()

        for image in image_list:
            extracted_img = pdf_file.extract_image(image[0])  # 0th item is xref
            image_bytes = extracted_img['image']
            image = Image.open(io.BytesIO(image_bytes))

            # fix the rotation
            image = image.rotate(90, expand=True)
            images.append(image)

    # try reading the text in the first image
    amy_image = None
    monday_datetime = None
    for image in images:
        text = pytesseract.image_to_string(image)
        if "Amy Pulsford" in text:
            amy_image = image
            # extract the start date
            lines = text.split("\n")
            for line in lines:
                if "ROSTER FOR" in line:
                    split_line = line.split(" ")
                    monday_date_str = split_line[2]  # should be of form dd/mm/yyyy
                    monday_date_str = monday_date_str  # + " +1000"  # Brisbane timezone is UTC+10
                    monday_datetime = datetime.strptime(monday_date_str, "%d/%m/%Y")  # %z is '+1000'
                    break
            break

    if monday_datetime is None:
        raise RuntimeError("[!] Couldn't find start date")
    print("[+] Monday date:", monday_datetime)

    if amy_image is None:
        raise RuntimeError("[!] Couldn't find image")

    print("[+] Found right page")
    if SHOW_IMAGES:
        amy_image.show()

    # PIL image to cv2 image https://stackoverflow.com/a/32264327
    amy_image_cv = cv.cvtColor(np.array(amy_image), cv.COLOR_RGB2BGR)
    sub_image = cv.imread("Amy cropped more.jpg")

    # find subimage in image https://stackoverflow.com/a/18075751
    result = cv.matchTemplate(amy_image_cv, sub_image, cv.TM_CCOEFF_NORMED)
    height_displacement, width_displacement = np.unravel_index(result.argmax(), result.shape)

    height = 65
    width = 2336

    # crop image to just amy's stuff
    just_amy_image = amy_image.crop(
        (0, height_displacement, width, height_displacement + height))
    if SHOW_IMAGES:
        just_amy_image.show()
    print("[+] Found the right row in the table")

    SEGMENTS = [350, 625, 895, 1170, 1445, 1715, 1990, 2260]
    days_of_the_week_text = []
    for index, left in enumerate(SEGMENTS):
        if index == len(SEGMENTS) - 1:
            break
        right = SEGMENTS[index + 1]
        segment = just_amy_image.crop((left, 0, right, height))
        text = pytesseract.image_to_string(segment)
        days_of_the_week_text.append(text)

    print("[+] Retrieved text from row")

    # temporarily use a makeshift Shift class
    from shift import Shift

    # parse the text so that the shifts are retrieved
    shifts = []  # list of 7 lists. Each list is a list of shifts that start on that day.
    for day_text in days_of_the_week_text:
        day_text = day_text.strip()

        if "Unavailable" in day_text:
            shifts.append([])
            continue

        day_lines = day_text.split("\n")
        if len(day_lines) == 1:
            # no break
            shift = Shift()
            split_day = day_lines[0].split(" ", maxsplit=1)

            shift.position = split_day[1]

            split_times = split_day[0].split("-")
            if len(split_times) != 2:
                print("[!] Couldn't parse the text:", day_text)
                continue
            shift.start = split_times[0]
            shift.end = split_times[1]

            shifts.append([shift])
        elif len(day_lines) == 2:
            # has a break

            first_half = Shift()
            second_half = Shift()
            split_day = day_lines[0].split(" ", maxsplit=1)

            first_half.position = split_day[1]
            second_half.position = split_day[1]

            split_times = split_day[0].split("-")
            if len(split_times) != 2:
                print("[!] Couldn't parse the text:", day_text)
                continue
            first_half.start = split_times[0]
            second_half.end = split_times[1]

            # now include the break
            if "Break" not in day_lines[1]:
                print("[!] Couldn't parse the text:", day_text)
                continue
            split_break = day_lines[1].split(" ")
            break_start = split_break[1]
            break_duration = split_break[3]
            first_half.end = break_start

            if len(break_start) != 4:
                print("[!] Couldn't parse the text:", day_text)
                continue

            hour = int(break_start[:2])
            minute = int(break_start[2:])

            minute += int(float(break_duration) * 60)
            if minute >= 60:
                hour += minute // 60
                minute = minute % 60
                hour = hour % 24
            hour_str = str(hour)
            if len(hour_str) < 2:
                hour_str = "0" + hour_str
            minute_str = str(minute)
            if len(minute_str) < 2:
                minute_str = "0" + minute_str
            break_end = hour_str + minute_str
            second_half.start = break_end

            shifts.append([first_half, second_half])
        else:
            print("[!] Couldn't parse the text:", day_text)
            continue

    print("[+] Retrieved shifts from text")

    # need to convert from above Shift instances into the dictionary instance that the other code wants
    # each shift is a dictionary of {start: datetime, end: datetime, id: str, position: str}
    actual_shifts = []
    SHIFT_ID = "Amy Work"

    def time_to_datetime(basis: datetime, time: str):
        hour = int(time[:2])
        minute = int(time[2:])
        return basis.replace(hour=hour, minute=minute)

    for day_index, day_shifts in enumerate(shifts):
        if not day_shifts:
            continue
        day_basis = monday_datetime + timedelta(days=day_index)
        if len(day_shifts) == 1:
            day_shift = day_shifts[0]
            start = time_to_datetime(day_basis, day_shift.start)
            end = time_to_datetime(day_basis, day_shift.end)
            if end < start:  # case where the end time is something like 0015: it ends on the next day
                end += timedelta(days=1)
            position = day_shift.position
            actual_shifts.append({'start': start, 'end': end, 'id': SHIFT_ID, 'position': position})

        elif len(day_shifts) == 2:
            first_half = day_shifts[0]
            second_half = day_shifts[1]
            first_start = time_to_datetime(day_basis, first_half.start)
            first_end = time_to_datetime(day_basis, first_half.end)
            second_start = time_to_datetime(day_basis, second_half.start)
            second_end = time_to_datetime(day_basis, second_half.end)

            if first_end < first_start:
                first_end += timedelta(days=1)
            if second_start < first_start:
                second_start += timedelta(days=1)
            if second_end < first_start:
                second_end += timedelta(days=1)
            actual_shifts.append({'start': first_start, 'end': first_end,
                                  'id': SHIFT_ID, 'position': first_half.position})
            actual_shifts.append({'start': second_start, 'end': second_end,
                                  'id': SHIFT_ID, 'position': second_half.position})
        else:
            raise RuntimeError("[!] Found more than two shifts on one day")

    print("[+] Converted shifts to right format")

    return actual_shifts


def main():
    for index, file in enumerate(FILES):
        shifts = retrieve_shifts_from_pdf(file)
        print(f"{index + 1}th files shifts:")
        for shift in shifts:
            print(shift)


if __name__ == "__main__":
    main()
