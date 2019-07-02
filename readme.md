# UTS Imass Bot

A Python bot written for the MicroRTS tournament.

For ease of installation several binary files were included in the repository.
Which include a slightly modified copy (see java files in Remote_MicroRTS_Java for changes).
The microrts jar is required so that the agent can perform self play as part of the pre-game-analysis.

Requires Python 3.6.

To run:
`python UTS_Imass_Server.py <path/to/tournament>`

where `<path/to/tournament>` is the folder holding the `readWriteFolder` location passed in the preGameAnalysis step, as the `readWriteFolder` is relative but `UTS_Imass_Server` needs to run in it's own folder.

Uses port 9823 and JSON for socket communication.

# Requirements

Requires a C++ library which is included as Python bindings for both Windows and Ubuntu. If this does not work, the library source can be retrieved [here](https://github.com/narsue/BLJPS_Python) and built with CMake.


# Usage
1. Run the python server first with a directory
2. Run the tournament mode
3. Run other modes (running other modes before a long pre-game-analysis period is given will cause the bot to run randomly)