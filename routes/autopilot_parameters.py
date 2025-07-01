from flask import Flask, render_template, url_for, request, redirect, Blueprint
from flask_sqlalchemy import SQLAlchemy

autopilot_parameters_page = Blueprint('autopilot_parameters_page', __name__, url_prefix='/autopilot_parameters')

storedAutopilotParameters = set()
storedNewAutopilotParameters = set()

# @route   GET autopilot_parameters/test
# @desc    Tests route
# @access  Public
@autopilot_parameters_page.route('/test')
def test_autopilot_parameters():
    return "autopilot_parameters route testing!"

# @route   GET autopilot_parameters/get
# @desc    Gets latest entry
# @access  Public
@autopilot_parameters_page.route('/get')
def get_autopilot_parameters():
    return str(storedAutopilotParameters)

# @route   GET autopilot_parameters/get_new
# @desc    Gets latest entry if the latest entry hasn't already been seen. 
#          If the latest entry has been seen, then simply send an empty dictionary.
#          This helps save on LTE data since we aren't sending data to the boat if 
#          it has already seen it.
# @access  Public
@autopilot_parameters_page.route('/get_new')
def get_new_autopilot_parameters():
    global storedNewAutopilotParameters
    toReturn = str(storedNewAutopilotParameters)
    storedNewAutopilotParameters = set()
    return toReturn

# @route   POST autopilot_parameters/set
# @desc    Add/save record
# @access  Public
@autopilot_parameters_page.route('/set', methods=["POST"])
def set_autopilot_parameters():
    global storedAutopilotParameters
    global storedNewAutopilotParameters

    try:
        data = request.get_json()
        newAutopilotParameters = data.get('value')
        storedAutopilotParameters = str(newAutopilotParameters)
        storedNewAutopilotParameters = str(newAutopilotParameters)
        return "autopilot_parameters updated successfully: " + str(storedAutopilotParameters)
    except:
        return "autopilot_parameters not updated successfully"
    
# @route   POST autopilot_parameters/delete
# @desc    deletes the current record (aka sets it to an empty dict {})
# @access  Public
@autopilot_parameters_page.route('/delete', methods=["POST"])
def delete_autopilot_parameters():
    global storedAutopilotParameters
    global storedNewAutopilotParameters
    storedAutopilotParameters = set()
    storedNewAutopilotParameters = set()
    return "autopilot_parameters deleted successfully!"