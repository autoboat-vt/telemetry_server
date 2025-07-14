from flask import Flask, render_template, url_for, request, redirect, Blueprint
from flask_sqlalchemy import SQLAlchemy

boat_status_page = Blueprint('boat_status_page', __name__, url_prefix='/boat_status')

storedBoatStatus = {}
storedNewBoatStatus = {}

# @route   GET boat_status/test
# @desc    Tests route
# @access  Public
@boat_status_page.route('/test')
def test_boat_status():
    return "boat_status route testing!"

# @route   GET boat_status/get
# @desc    Gets latest entry
# @access  Public
@boat_status_page.route('/get')
def get_boat_status():
    return storedBoatStatus

# @route   GET boat_status/get_new
# @desc    Gets latest entry if the latest entry hasn't already been seen. 
#          If the latest entry has been seen, then simply send an empty dictionary.
#          This helps save on LTE data since we aren't sending data to the boat if 
#          it has already seen it.
# @access  Public
@boat_status_page.route('/get_new')
def get_new_boat_status():
    global storedNewBoatStatus
    toReturn = storedNewBoatStatus
    storedNewBoatStatus = {}
    return toReturn

# @route   POST boat_status/set
# @desc    Add/save record
# @access  Public
@boat_status_page.route('/set', methods=["POST"])
def set_boat_status():
    global storedBoatStatus
    global storedNewBoatStatus

    try:
        data = request.get_json()
        newBoatStatus = data.get('value')
        storedBoatStatus = newBoatStatus
        storedNewBoatStatus = newBoatStatus
        return "boat_status updated successfully: " + str(storedBoatStatus)
    except:
        return "boat_status not updated successfully"