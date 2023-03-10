#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2020 by Harald Klein <hari@vt100.at> - All rights reserved
# 

import os
import logging
import logging.handlers
import threading

import chess.pgn
import chess

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

# certabo helpers
import codes
import serialreader
from utils.usbtool import find_address

CERTABO_DATA_PATH = r"certabo\utils\data"
# TODO: Fix this, move it into certabo function
os.makedirs(CERTABO_DATA_PATH, exist_ok=True)


class Certabo:
    def __init__(self, calibrate=0, port=None, **kwargs):
        super().__init__(**kwargs)
        if port is None:
            self.portname = find_address()
        else:
            self.portname = port

        if calibrate:
            self.calibration = True
        else:
            self.calibration = False
        if calibrate > 1:
            self.new_setup = True
        else:
            self.new_setup = False
        self.rotate180 = False
        self.color = chess.WHITE
        self.starting_position = chess.STARTING_FEN
        self.chessboard = chess.Board(chess.STARTING_FEN)
        self.board_state_usb = ""
        self.mystate = "init"
        self.reference = ""
        self.move_event = threading.Event()
        self.wait_for_move = False
        self.pending_moves = []

        # internal values for CERTABO board
        self.calibration_samples_counter = 0
        self.calibration_samples = []
        self.usb_data_history_depth = 3
        self.usb_data_history = list(range(self.usb_data_history_depth))
        self.usb_data_history_filled = False
        self.usb_data_history_i = 0
        self.move_detect_tries = 0
        self.move_detect_max_tries = 3

        # try to load calibration data (mapping of RFID chip IDs to pieces)
        calibration_file = f'calibration-{self.portname.replace("/", "").replace(":", "")}.bin'
        self.calibration_filepath = os.path.join(CERTABO_DATA_PATH, calibration_file)
        print(f'calibration file: {self.calibration_filepath}')
        codes.load_calibration(self.calibration_filepath)

        # spawn a serial thread and pass our data handler
        self.serialthread = serialreader.serialreader(self.handle_usb_data, self.portname)
        self.serialthread.daemon = True
        self.serialthread.start()

    def get_user_move(self):
        self.wait_for_move = True
        logging.debug('waiting for event signal')
        self.move_event.wait()
        self.move_event.clear()
        logging.debug(f'event signal received, pending moves: {self.pending_moves}')
        self.wait_for_move = False
        return self.pending_moves 

    def get_reference(self):
        return self.reference

    def set_reference(self, reference):
        self.reference = reference

    def get_color(self):
        return self.color

    def set_color(self, color):
        self.color = color

    def set_state(self, state):
        self.mystate = state

    def get_state(self):
        return self.mystate

    def new_game(self):
        self.chessboard = chess.Board()
        self.mystate = "init"

    def set_board_from_fen(self, fen):
        self.chessboard = chess.Board(fen)

    def send_leds(self, message:bytes=(0).to_bytes(8,byteorder='big',signed=False)):
        # logging.info(f'sending LED: {message}')
        self.serialthread.send_led(message)

    def diff_leds(self):
        s1 = self.chessboard.board_fen()
        s2 = self.board_state_usb.split(" ")[0]
        if (s1 != s2):
            diffmap = codes.diff2squareset(s1, s2)
            # logging.debug(f'Difference on Squares:\n{diffmap}')
            self.send_leds(codes.squareset2ledbytes(diffmap))
        else:
            self.send_leds()

    def handle_usb_data(self, data):
        usb_data = list(map(int, data.split(" ")))
        if self.calibration == True:
            self.calibrate_from_usb_data(usb_data)
        else:
            if self.usb_data_history_i >= self.usb_data_history_depth:
                self.usb_data_history_filled = True
                self.usb_data_history_i = 0

            self.usb_data_history[self.usb_data_history_i] = list(usb_data)[:]
            self.usb_data_history_i += 1
            if self.usb_data_history_filled:
                self.usb_data_processed = codes.statistic_processing(self.usb_data_history, False)
                if self.usb_data_processed != []:
                    test_state = codes.usb_data_to_FEN(self.usb_data_processed, self.rotate180)
                    # print(test_state)
                    if test_state != "":
                        if self.board_state_usb != test_state:
                            new_position = True
                        else:
                            new_position = False
                        self.board_state_usb = test_state
                        self.diff_leds()
                        if new_position:
                            # new board state via usb
                            # logging.info(f'info string FEN {test_state}')
                            if self.wait_for_move:
                                logging.debug('trying to find user move in usb data')
                                try:
                                    self.pending_moves = codes.get_moves(self.chessboard, self.board_state_usb, 1) # only search one move deep
                                    if self.pending_moves != []:
                                        logging.debug('firing event')
                                        # self.chessboard.push_uci(self.pending_moves[0])
                                        self.move_event.set()
                                except:
                                    self.pending_moves = []

    def calibrate_from_usb_data(self, usb_data):
        self.calibration_samples.append(usb_data)
        logging.info("    adding new calibration sample")
        self.calibration_samples_counter += 1
        if self.calibration_samples_counter >= 15:
            logging.info( "------- we have collected enough samples for averaging ----")
            usb_data = codes.statistic_processing_for_calibration(self.calibration_samples, False)
            codes.calibration(usb_data, self.new_setup, self.calibration_filepath)
            self.calibration = False
            logging.info('calibration ok') 
            self.send_leds()
        elif self.calibration_samples_counter %2:
            self.send_leds(b'\xff\xff\x00\x00\x00\x00\xff\xff')
        else:
            self.send_leds()
