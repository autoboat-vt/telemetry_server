from flask import Flask, render_template, url_for, request, redirect, Blueprint
from flask_sqlalchemy import SQLAlchemy

waypoints_page = Blueprint('waypoints_page', __name__, url_prefix='/waypoints')

storedWaypoints = {}
storedNewWaypoints = {}

# @route   GET waypoints/test
# @desc    Tests route
# @access  Public
@waypoints_page.route('/test')
def test_waypoints():
    return "waypoints route testing!"

# @route   GET waypoints/get
# @desc    Gets latest entry
# @access  Public
@waypoints_page.route('/get')
def get_waypoints():
    return storedWaypoints

# @route   GET waypoints/get_new
# @desc    Gets latest entry if the latest entry hasn't already been seen. 
#          If the latest entry has been seen, then simply send an empty dictionary.
#          This helps save on LTE data since we aren't sending data to the boat if 
#          it has already seen it.
# @access  Public
@waypoints_page.route('/get_new')
def get_new_waypoints():
    global storedNewWaypoints
    toReturn = storedNewWaypoints
    storedNewWaypoints = {}
    return toReturn

# @route   POST waypoints/set
# @desc    Add/save record
# @access  Public
@waypoints_page.route('/set', methods=["POST"])
def set_waypoints():
    global storedWaypoints
    global storedNewWaypoints

    try:
        data = request.get_json()
        newWaypoints = data.get('value')
        storedWaypoints = newWaypoints
        storedNewWaypoints = newWaypoints
        return "waypoints updated successfully: " + str(storedWaypoints)
    except:
        return "waypoints not updated successfully"

# @route   POST waypoints/delete
# @desc    deletes the current record (aka sets it to an empty dict {})
# @access  Public
@waypoints_page.route('/delete', methods=["POST"])
def delete_waypoints():
    global storedWaypoints
    global storedNewWaypoints
    storedWaypoints = {}
    storedNewWaypoints = {}
    return "waypoints deleted successfully!"