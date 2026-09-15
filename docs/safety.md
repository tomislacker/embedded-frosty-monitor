# Safety

This unit gets installed inside live commercial equipment. Read this
before installing, servicing, or removing a logger from a machine. See
also the model-specific procedure in
[docs/install-guides/137A.md](install-guides/137A.md).

## Line-voltage work

Installing the CT clamps around the beater and compressor current-carrying
conductors, and tapping the opto-isolated inputs onto the 120V beater leg
and 24VAC contactor coil, is line-voltage work. It must only be done by a
qualified technician, with the machine unplugged and locked out, for the
entire duration of sensor installation. Do not work inside the machine's
electrical enclosure or junction box with the machine powered.

## Power the DAQ from a separate outlet

The logger's external USB-C power adapter plugs into its own, separate
wall outlet. It never shares, taps, or is powered from the machine's
dedicated 20A circuit. The machine is rated up to 12A single-phase on that
circuit already; the logger has no business drawing from it, and doing so
would also make it impossible to fully de-energize the machine for service
without also killing the logger.

## Placement

Nothing about this unit — core, pods, or cabling — is mounted in the
food-product zone, or anywhere it could fall, drop, or work loose into
product. Cable runs and pod mounting points are chosen and secured with
that constraint first, sensor placement quality second.

Leak sensors carry the same constraint plus one of their own: the drop
counter must never obstruct or restrict the drip tube's drain path, and the
moisture pad and its cabling must not create a trip or snag hazard for
anyone working under or around the machine.

## Airflow

Do not mount anything, or route any cable, in a way that obstructs
condenser airflow. Maintain the machine's rated clearances — 8 inches at
the sides and rear — for the condenser intake and exhaust. A logger that
causes the condenser to run hotter is actively working against the
diagnostic it's there to support.

## Panels and moving parts

The machine must not be run with side or rear panels removed except by a
qualified technician actively performing the install or retrieval, and
only for as long as that takes. Once sensors are placed, all in-machine
wiring is secured — dressed, tied, clear — away from the belt/gear drive,
flywheel, and any other moving parts before the panels go back on and the
machine is returned to service.

## Only low-voltage DC inside the logger enclosure

The logger enclosure itself never has line voltage inside it. The only
thing that enters the box is regulated 5V DC from the external adapter.
CT clamps, opto-isolated inputs, and all other sensor connections are
selected and wired specifically so that no AC line voltage is ever present
inside the enclosure.

## Heat

The compressor compartment runs hot, especially during and after
freeze-down cycles. Route cables and mount pods with that in mind — away
from the compressor shell and discharge line where routing allows, and
rated for the ambient they'll actually see if not.

## Disclaimer

This document describes safety practices specific to installing this
logger. It is not a substitute for the Frosty Factory manufacturer's
service manual, the machine's own safety documentation, or local
electrical code. Where they conflict, the manufacturer's documentation and
code take precedence.
