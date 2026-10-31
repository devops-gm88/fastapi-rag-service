# Alert rules

There are 7 alert rules in the pilot.

| Rule | Trigger |
|---|---|
| geofence_exit | A vehicle leaves its depot zone |
| fuel_drop | Fuel level falls more than 15 percent in one hour |
| door_open | A door opens while the ignition is off |
| idle_long | Idle time exceeds 45 minutes |
| no_ping | No reading for 30 minutes |
| speed_cap | Speed exceeds 110 km/h |
| odometer_jump | Odometer rises more than 500 km in one hour |

Each rule writes one row to the alert table. The rule name is stored with the row.
