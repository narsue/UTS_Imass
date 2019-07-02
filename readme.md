# UTS Imass Bot

A Python bot written for the MicroRTS tournament.

Requires Python 3.6.

To run:
`python UTS_Imass_Server.py <path/to/tournament>`

where `<path/to/tournament>` is the folder holding the `readWriteFolder` location passed in the preGameAnalysis step, as the `readWriteFolder` is relative but `UTS_Imass_Server` needs to run in it's own folder.

Uses port 9823 and JSON for socket communication.

# Requirements

Requires a C++ library which is included as Python bindings for both Windows and Ubuntu. If this does not work, the library source can be retrieved [here](https://github.com/narsue/BLJPS_Python) and built with CMake.