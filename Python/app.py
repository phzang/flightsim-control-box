# Main display script
# Uses pygame.joystick for the toggle switches
# __main__ function has 3 threads:
# 1. joystick (toggle swithches)
# 2. arduino (rotary dials and buttons)
# 3. display (7 segment display)

#from lib2to3.pytree import convert
import logging
import threading
from threading import Lock
from queue import Queue
import time
import sys
import traceback
import os
import serial
import pygame
import pygame.locals
import keyboard

from arduino_dictionary import arduino_dictionary
from toggle_switch_dictionary import toggle_switch_dictionary

from SimConnect import *
from transponder import *
from com import *
from nav import *
from prop import *
from mixture import *
from helpers import *
from globals import DEBUG

prev_time = time.time()
current_time = time.time()

lock = threading.Lock()

# Open Arduino Serial Port
serial_port =  serial.Serial('COM3', 9600, timeout=0)

#display_serial_port =  serial.Serial('COM6', 9600, timeout=0)
display_serial_port = 0

# True of serial display is plugged in
display_serial_port_active = False

#SimConnect link
sim_connect = SimConnect()
aircraft_requests = AircraftRequests(sim_connect, _time=0)
aircraft_events = AircraftEvents(sim_connect)

# Sets default values before SimConnect updates them
AIRCRAFT_TYPE = 0

DISPLAY_XPNDR = 0 # display transponder
DISPLAY_COM_ACTIVE1 = 0 # display
DISPLAY_COM_STANDBY1 = 0 # display
DISPLAY_NAV_ACTIVE1 = 0 # display
DISPLAY_NAV_STANDBY1 = 0

DISPLAY_COM_ACTIVE2 = 0 # display
DISPLAY_COM_STANDBY2 = 0 # display
DISPLAY_NAV_ACTIVE2 = 0 # display
DISPLAY_NAV_STANDBY2 = 0

COM_UPDATE = False
NAV_UPDATE = False
XPNDR_UPDATE = False

# start with primary
COM_DIAL = CommunicationSelect.Primary

def update_com():
    # Only update the display what is needed
    # It causes a delay if trying to update everything at once
    global DISPLAY_COM_ACTIVE1
    global DISPLAY_COM_ACTIVE2
    global DISPLAY_COM_STANDBY1
    global DISPLAY_COM_STANDBY2
    global COM_DIAL

    COM_DIAL = get_com_dial()

    if DEBUG: print("update_com()")

    if COM_DIAL == CommunicationSelect.Primary:
        temp_com_active1 = aircraft_requests.get('COM_ACTIVE_FREQUENCY:1')
        temp_com_standby1 = aircraft_requests.get('COM_STANDBY_FREQUENCY:1')
        # Only update number if different, prevents display from blinking when updating
        if temp_com_standby1 != DISPLAY_COM_STANDBY1:
            DISPLAY_COM_STANDBY1 = temp_com_standby1
            if display_serial_port_active: display_serial_port.write(bytes("g" + str(DISPLAY_COM_STANDBY1) + "\n",'utf-8'))
            if DEBUG: print(bytes("g" + str(DISPLAY_COM_STANDBY1) + "\n",'utf-8'))
            if temp_com_active1 != DISPLAY_COM_ACTIVE1:
                DISPLAY_COM_ACTIVE1 = temp_com_active1
                display_serial_port.write(bytes("o" + str(DISPLAY_COM_ACTIVE1) + "\n",'utf-8'))
                if DEBUG: print(bytes("o" + str(DISPLAY_COM_ACTIVE1) + "\n",'utf-8'))

    if COM_DIAL == CommunicationSelect.Secondary:
        temp_com_active2 = aircraft_requests.get('COM_ACTIVE_FREQUENCY:2')
        temp_com_standby2 = aircraft_requests.get('COM_STANDBY_FREQUENCY:2')
        # Only update number if different, prevents display from blinking when updating
        if temp_com_standby2 != DISPLAY_COM_STANDBY2:
            DISPLAY_COM_STANDBY2 = temp_com_standby2
            if display_serial_port_active: display_serial_port.write(bytes("g" + str(DISPLAY_COM_STANDBY2) + "\n",'utf-8'))
            if DEBUG: print(bytes("g" + str(DISPLAY_COM_STANDBY2) + "\n",'utf-8'))
            if temp_com_active2 != DISPLAY_COM_ACTIVE2:
                DISPLAY_COM_ACTIVE2 = temp_com_active2
                if display_serial_port_active: display_serial_port.write(bytes("o" + str(DISPLAY_COM_ACTIVE2) + "\n",'utf-8'))
                if DEBUG: print(bytes("o" + str(DISPLAY_COM_ACTIVE2) + "\n",'utf-8'))

def update_nav():
    # Currently do not have 7 segment displays connected for navation
    pass
    DISPLAY_NAV_ACTIVE1 = aircraft_requests.get('NAV_ACTIVE_FREQUENCY:1')
    if display_serial_port_active: display_serial_port.write(bytes("o" + str(DISPLAY_NAV_ACTIVE1) + "\n",'utf-8'))

def update_xpndr():
    global DISPLAY_XPNDR
    temp_xpndr = float(get_xpndr())*0.00001 # make display read 0.0xxxx...
                                            # last 4 digits tranponder code
    # Only update number if different, prevents display from blinking when updating
    if temp_xpndr != DISPLAY_XPNDR:
        DISPLAY_XPNDR = temp_xpndr
        if display_serial_port_active: display_serial_port.write(bytes("r" + str(DISPLAY_XPNDR) + "\n",'utf-8'))

def get_xpndr():
    # get() returns a hex version of an int
    transponder = hex(int(aircraft_requests.get('TRANSPONDER_CODE:1')))
    # removes the beginning 0x because it's a hex
    return int(transponder.lstrip("0x"))

# --------------------- START JOYSTICK ITEMS --------------------------------
FPS = 30

pygame.init()
pygame.joystick.init()

# Finds the button box joystick from USB devices and initializes it
for x in range(pygame.joystick.get_count()):
    joystick = pygame.joystick.Joystick(x)
    joystick.init()
    if joystick.get_name() == "Generic USB Joystick":
        break

def joystick_main_thread(blank):
    convert_key = 'NONE' # byte identifier to SimConnect identifier holder
    event_function = 0
    while True:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.JOYBUTTONDOWN:
                if DEBUG:
                    print(event.dict, event.joy,
                    toggle_switch_dictionary[AIRCRAFT_TYPE][str(event.button)], 'pressed')
                if verify_toggle_switch_dictionary(str(event.button), AIRCRAFT_TYPE):
                    convert_key = toggle_switch_dictionary[AIRCRAFT_TYPE][str(event.button)]
                else:
                    convert_key = 'NONE'
            elif event.type == pygame.JOYBUTTONUP:
                if DEBUG:
                    print(event.dict, event.joy,
                    toggle_switch_dictionary[AIRCRAFT_TYPE][str(event.button)], 'released')
                if verify_toggle_switch_dictionary(str(event.button), AIRCRAFT_TYPE):
                    convert_key = toggle_switch_dictionary[AIRCRAFT_TYPE][str(event.button)]
                else:
                    convert_key = 'NONE'
            #elif event.type == pygame.KEYDOWN:
            #   if event.key == pygame.K_KP0:

            if convert_key == 'ENGINE_MASTER':
                # Does not work currently, MSFS doesn't recognize pygame keyboard events, why?
                # keyboard.press_and_release('0')
                # newevent = pygame.event.Event(pygame.locals.KEYDOWN, unicode="a", key=pygame.locals.K_KP0,
                # mod=pygame.locals.KMOD_NONE) #create the event
                # pygame.event.post(newevent) #add the event to the queue
                # time.sleep(0.01)
                # newevent = pygame.event.Event(pygame.locals.KEYUP, unicode="a", key=pygame.locals.K_KP0,
                # mod=pygame.locals.KMOD_NONE) #create the event
                # pygame.event.post(newevent) #add the event to the queue
                convert_key = 'NONE'

            elif convert_key != 'NONE':
                # Looks up and executes SimConnect function
                try:
                    if DEBUG:
                        print("FINAL CONVERT KEY ",convert_key)
                    event_function = aircraft_events.find(convert_key)
                    event_function()
                except TypeError:
                    pass

        time.sleep(1/FPS)
# --------------------- END JOYSTICK ITEMS ----------------------------------




# --------------------- START DIAL ITEMS ------------------------------------
def arduino_main_thread(blank):
    convert_key = 'NONE'
    event_function = 0
    global prev_time
    global current_time
    global COM_UPDATE
    global NAV_UPDATE
    global XPNDR_UPDATE
    global AXIS_PROPELLER # from prop.py
    set_cache_values()
    while True:
        current_time = time.time()
        try:
            ser = serial_port.read()
            if ser:
                #altitude = aircraft_requests.get("PLANE_ALTITUDE")
                #print(altitude)

                if DEBUG:
                    print_arduino_lookup(ser.hex())
                if DEBUG:
                    print(is_transponder(ser.hex()))

                convert_key = convert_arduino_input(ser.hex())

                # if com swap button pressed
                if ser.hex == "06":
                    convert_key = com_swap_com()

                # key won't turn off, have to manually turn off through the cockpit
                # if key is turned
                elif ser.hex() == "53":
                    if AIRCRAFT_TYPE == "MODEL_DA40":
                        convert_key = "TOGGLE_MASTER_BATTERY"

                # if key is turned all the way to start
                elif ser.hex() == "52":
                    if AIRCRAFT_TYPE in ("MODEL_DA40", "Optica", "MODEL_ARROW"):
                        convert_key = "MAGNETO_START"

                # controls mixture for planes that have a mixture lever
                elif ser.hex() == "30" or ser.hex() == "31":
                    if AIRCRAFT_TYPE == "MODEL_ARROW":
                        lock.acquire()
                        if ser.hex() == "30":
                            increase_mixture_position()
                        elif ser.hex() == "31":
                            decrease_mixture_position()
                        lock.release()           
                        event_function = aircraft_events.find('AXIS_MIXTURE_SET')
                        event_function(get_axis_mixture_position())
                    else:
                        convert_key = return_transponder_arduino_lookup(ser.hex())

                # controls rpm for planes that have a prop rpm lever
                elif ser.hex() == "10" or ser.hex() == "11":
                    if AIRCRAFT_TYPE == "MODEL_ARROW":
                        lock.acquire()
                        if ser.hex() == "10":
                            increase_prop_position()
                        elif ser.hex() == "11":
                            decrease_prop_position()
                        lock.release()                                        
                        event_function = aircraft_events.find('AXIS_PROPELLER_SET')
                        event_function(get_axis_prop_position())
                    else:
                        convert_key = return_transponder_arduino_lookup(ser.hex())


                # if transponder dials pressed
                elif ser.hex() == "38" or ser.hex() == "39" or ser.hex() == "40":
                    convert_key = return_transponder_arduino_lookup(ser.hex())
                    lock.acquire()
                    XPNDR_UPDATE = True
                    lock.release()

                # if communication dials pressed
                elif (int(ser.hex()) >= 18 and int(ser.hex()) <= 24):
                    convert_key = return_com_arduino_lookup(ser.hex())
                    lock.acquire()
                    COM_UPDATE = True
                    lock.release()
                    if DEBUG: print("COM_UPDATE ", COM_UPDATE)

                # if navigation dials pressed
                elif (int(ser.hex()) >= 42 and int(ser.hex()) <= 48):
                    convert_key = return_nav_arduino_lookup(ser.hex())
                    lock.acquire()
                    NAV_UPDATE = True
                    lock.release()

                # Resets trim for different aircraft types
                # Each aircraft starts with a different default trim level
                elif int(ser.hex()) == 28:
                    event_function = aircraft_events.find('AXIS_ELEV_TRIM_SET')
                    # if DEBUG: print(AIRCRAFT_TYPE)
                    if AIRCRAFT_TYPE == "MODEL_C152":
                        event_function(0)
                    elif AIRCRAFT_TYPE == "MODEL_DA40":
                        event_function(1300)
                    else: event_function(0)

                if convert_key != 'NONE':
                    try:
                        if DEBUG:
                            print("FINAL CONVERT KEY ",convert_key)
                        event_function = aircraft_events.find(convert_key)
                        event_function()

                        if ser.hex() == "06":
                            # if com swap button is pressed
                            lock.acquire()
                            COM_UPDATE = True
                            lock.release()
                        if COM_UPDATE:
                            # resets time for updating the 7 digit display
                            prev_time = time.time()
                        elif NAV_UPDATE:
                            # Currently no 7 digit display for navigation
                            pass
                            #update_nav()
                        elif XPNDR_UPDATE:
                            # Currently no 7 digit display for transponder
                            pass
                            #update_xpndr()

                    except TypeError:
                        pass

            time.sleep(0.01)
            ser = 0 # Reset serial data
        except serial.SerialTimeoutException:
            print('Data could not be read')
            time.sleep(0.01)

        if ((COM_UPDATE or XPNDR_UPDATE) and (current_time - prev_time) > 2):            
            # This keeps the display update thread going for 2 seconds after
            # a dial was moved, otherwise there will be missed inputs
            print("False")
            lock.acquire()
            COM_UPDATE = False
            NAV_UPDATE = False
            XPNDR_UPDATE = False
            lock.release()
            prev_time = time.time()

# --------------------- END DIAL ITEMS --------------------------------------


def thread_function(name):
    print("Thread %s: starting", name)
    time.sleep(2)
    print("Thread %s: ending", name)

def print_display():
    # Print display in console for debug purposes
    global AIRCRAFT_TYPE
    global DISPLAY_XPNDR
    global DISPLAY_COM_ACTIVE1
    global DISPLAY_COM_ACTIVE2
    global DISPLAY_COM_STANDBY1
    global DISPLAY_COM_STANDBY2

    global DISPLAY_NAV_ACTIVE1
    global DISPLAY_NAV_ACTIVE2
    global DISPLAY_NAV_STANDBY1
    global DISPLAY_NAV_STANDBY2

    # returns DEFAULT if aircraft is not a supported aircraft
    AIRCRAFT_TYPE = get_aircraft_type(aircraft_requests)
    print("Current aircraft type is", AIRCRAFT_TYPE)

    DISPLAY_XPNDR = get_xpndr()
    print("Transponder: ", DISPLAY_XPNDR)
    DISPLAY_COM_ACTIVE1 = aircraft_requests.get('COM_ACTIVE_FREQUENCY:1')
    DISPLAY_COM_ACTIVE2 = aircraft_requests.get('COM_ACTIVE_FREQUENCY:2')
    DISPLAY_COM_STANDBY1 = aircraft_requests.get('COM_STANDBY_FREQUENCY:1')
    DISPLAY_COM_STANDBY2 = aircraft_requests.get('COM_STANDBY_FREQUENCY:2')

    #display_serial_port.write(bytes("g" + str(DISPLAY_COM_STANDBY1) + "\n",'utf-8'))
    #display_serial_port.write(bytes("o" + str(DISPLAY_COM_ACTIVE1) + "\n",'utf-8'))


    print("COM ACTIVE1: ", format(DISPLAY_COM_ACTIVE1, '.3f'))
    print("COM STANDBY1: ", format(DISPLAY_COM_STANDBY1, '.3f'))
    print("COM ACTIVE2: ", format(DISPLAY_COM_ACTIVE2, '.3f'))
    print("COM STANDBY2: ", format(DISPLAY_COM_STANDBY2, '.3f'))

    DISPLAY_NAV_ACTIVE1 = aircraft_requests.get('NAV_ACTIVE_FREQUENCY:1')
    DISPLAY_NAV_ACTIVE2 = aircraft_requests.get('NAV_ACTIVE_FREQUENCY:2')
    DISPLAY_NAV_STANDBY1 = aircraft_requests.get('NAV_STANDBY_FREQUENCY:1')
    DISPLAY_NAV_STANDBY2 = aircraft_requests.get('NAV_STANDBY_FREQUENCY:2')

    print("NAV ACTIVE1: ", format(DISPLAY_NAV_ACTIVE1, '.3f'))
    print("NAV STANDBY1: ", format(DISPLAY_NAV_STANDBY1, '.3f'))
    print("NAV ACTIVE2: ", format(DISPLAY_NAV_ACTIVE2, '.3f'))
    print("NAV STANDBY2: ", format(DISPLAY_NAV_STANDBY2, '.3f'))

def update_display_thread(input):
    # Only run update functions if needed
    while True:
        global COM_UPDATE
        global NAV_UPDATE
        global XPNDR_UPDATE

        if COM_UPDATE: update_com()
        if XPNDR_UPDATE: update_xpndr()
        time.sleep(0.001)

def set_cache_values():
    frequency = aircraft_requests.find('COM_ACTIVE_FREQUENCY:1')
    frequency.time = 0
    frequency = aircraft_requests.find('COM_ACTIVE_FREQUENCY:2')
    frequency.time = 0
    frequency = aircraft_requests.find('COM_STANDBY_FREQUENCY:1')
    frequency.time = 0
    frequency = aircraft_requests.find('COM_STANDBY_FREQUENCY:2')
    frequency.time = 0


if __name__ == '__main__':
    # Three threads:
    # 1. joystick from pygame.joystick is for toggle switches
    # 2. arduino contains the dials and buttons
    # 3. display contains the 7 segment displays, WIP
    print_display()

    try:
        joystick_thread = threading.Thread(target=joystick_main_thread, args=(1,),
            daemon=True)
        joystick_thread.start()
        arduino_thread = threading.Thread(target=arduino_main_thread, args=(1,),
            daemon=True)
        arduino_thread.start()
        display_thread = threading.Thread(target=update_display_thread, args=(1,),
            daemon=True)
        display_thread.start()
        while True:
            pass
    except KeyboardInterrupt:
        print("Program End")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
    except ConnectionError:
        print("Cannot connect to SimConnect")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
