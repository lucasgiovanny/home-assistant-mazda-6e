# Introduction

This component has been created to be used with Home Assistant.

Mazda 6e presents a possibility to connect your Mazda 6e vehicle to Home Assistant.
This integration accepts your email and password and encrypts them internally. A device ID is generated automatically and retained for reauthentication. Enter the verification code sent by email when requested. Plaintext credentials and passwords are not saved in the config entry.

The integration exposes a lock entity for the vehicle doors. Mazda's six-digit Control Passcode can be entered during setup or later through **Reconfigure**. The lock entity remains unavailable until the passcode and control key have been configured. Normal Home Assistant lock and unlock actions do not ask for a code.

# Installation

## With HACS

1. Add this repository as a custom repository in HACS.
2. Download the integration.
3. Restart Home Assistant

## Manual

Copy the `mazda_6e` directory, from `custom_components` in this repository,
and place it inside your Home Assistant Core installation's `custom_components` directory. Restart Home Assistant prior to moving on to the `Setup` section.

`Note`: If installing manually, in order to be alerted about new releases, you will need to subscribe to releases from this repository

# Cloud-control passcode

The Control Passcode is required by Mazda for cloud vehicle controls. Bluetooth control in the Mazda app does not request it, so disable Bluetooth on the phone or move outside Bluetooth range before looking for the prompt:

1. Open the Mazda app with Bluetooth disabled or while outside Bluetooth range of the vehicle.
2. Start a cloud vehicle-control action, such as locking or unlocking the doors.
3. Enter the requested six-digit Control Passcode. If it is unknown, use **Forgot PWD** in the Mazda app to reset it.
4. In Home Assistant, open the Mazda 6e integration and select **Reconfigure**.
5. Enter the Mazda account credentials and the same six-digit Control Passcode.

Reconfiguration signs in again and registers the control key required for signed cloud commands. The passcode is stored in the Home Assistant config entry as an integration credential. It is encrypted before being sent to Mazda and is never exposed as a code field on the lock entity.

# Charging controls

- **Charge limit** (number, 60–100 %) is created whenever the vehicle reports a target state of charge, even if Mazda's function list does not advertise it.
- **Charge schedules** (sensor) shows the number of charging schedules, with each schedule's start, end and active state as attributes.
- **Charge schedule start**, **Charge schedule end** (time) and **Charge schedule** (switch) edit the first schedule. Create the schedule in the Mazda app first; these controls stay unavailable until one exists. Times are sent with Home Assistant's current UTC offset.

- **Charge status** keeps the raw Mazda code in its `status_code` attribute, since several codes are not mapped yet.
- **Refresh vehicle status** (button) asks the vehicle to upload fresh data instead of waiting for its next report.

All charging controls require the control key registered through **Reconfigure**, but not the Control Passcode.

# Trips

The integration keeps a log of the last 100 trips, built from the vehicle's driving/parked status, the odometer and the state of charge. A trip starts when the vehicle reports *driving* and the odometer moves, and ends once it has been parked for 5 minutes, so short stops stay inside the same trip. Remote climate before leaving also reports *driving*, but with the car standing still it is not counted. The log survives Home Assistant restarts.

- **Last trip** (sensor, km) has the latest trip's start, end, duration, distance, state of charge used, estimated energy, consumption and average speed as attributes, plus `recent_trips` with the last 30 trips.
- **Distance this month**, **Energy this month**, **Consumption this month** and **Trips this month** (sensors) total the current calendar month and reset on the 1st.
- Each finished trip fires a `mazda_6e_trip` event with the same fields and the `vehicle_id`.

Energy is estimated from the state of charge, so it includes everything the battery supplied while driving, such as climate. The API reports the state of charge in whole percent, so a trip that used under 2% takes its energy from the average consumption of the last 20 trips that used 5% or more, and is marked `estimated`. The battery capacity used for it defaults to 68.8 kWh and can be changed under **Configure** for the long-range battery. The Mazda API reports no location, so trips have no start or end place.

# Charging sessions

The integration also keeps a log of the last 100 charging sessions. A session runs from plugging in (AC cable or DC gun) to unplugging, so pauses in between, such as solar charging stopping and resuming, stay inside the same session. Plugging in without the car ever charging is not logged. The log survives Home Assistant restarts.

- **Last charge** (sensor, kWh) has the latest session's start (plug-in), when charging actually began and last ran (`charging_start` and `charging_end`, inside the plug-in for scheduled or solar charges), end (unplug or full battery), duration, time actually charging, state of charge at start and end, estimated energy, type (`AC` or `DC`) and peak current as attributes, plus `recent_charges` with the last 30 sessions.
- Each finished session fires a `mazda_6e_charge` event with the same fields and the `vehicle_id`.

Energy is estimated from the state of charge with the same battery capacity as trips, so it is what reached the battery, without charging losses.

# Services

| Service | Fields | Notes |
|---|---|---|
| `mazda_6e.create_charge_schedule` | `device_id`, `start_time`, optional `end_time` | Only when the vehicle has no charging schedule. |
| `mazda_6e.delete_charge_schedule` | `device_id` | Deletes the first charging schedule. |
| `mazda_6e.create_battery_preheating` | `device_id`, `departure_time` | Only when the vehicle has no battery-preheating plan. Preheating starts 20 minutes before departure. The plan can then be edited and disabled with its time and switch entities; deleting it is only possible in the Mazda app. |
