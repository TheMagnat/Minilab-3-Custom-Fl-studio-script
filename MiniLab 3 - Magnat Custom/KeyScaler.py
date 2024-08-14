
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEY_TO_POSITION = [0, -1, 1, -1, 2, 3, -1, 4, -1, 5, -1, 6]

KNOWN_SCALE = [
    ("Major", [0, 2, 4, 5, 7, 9, 11]),
    ("Minor Natural", [0, 2, 3, 5, 7, 8, 10])
    # Add new scale here, it must have a name and a list of 7 notes (corresponding to the 7 whites notes to map)
]

# Default scale and root note
DEFAULT_ROOT_NOTE = NOTE_NAMES.index("B")
DEFAULT_SCALE = 1 # Minor natural

#B Minor natural
#F Major

class KeyScaler:

    def __init__(self) -> None:
        self.currentScaleIndex = DEFAULT_SCALE
        self.updateScale()

        self.currentRoot = DEFAULT_ROOT_NOTE
        self.currentRootName = NOTE_NAMES[self.currentRoot]

    def setRootNote(self, note):
        self.currentRoot = note
        self.currentRootName = NOTE_NAMES[note]

    def previousScale(self):
        self.currentScaleIndex = (self.currentScaleIndex-1) % len(KNOWN_SCALE)
        self.updateScale()
    
    def nextScale(self):
        self.currentScaleIndex = (self.currentScaleIndex+1) % len(KNOWN_SCALE)
        self.updateScale()
    
    def updateScale(self):
        self.currentScaleName = KNOWN_SCALE[self.currentScaleIndex][0]
        self.currentScale = KNOWN_SCALE[self.currentScaleIndex][1]

    def getCurrentScaleName(self):
        return f"{self.currentRootName} - {self.currentScaleName}"

    def getEventNote(self, event):
        return event.data1 % 12

    def scaleEvent(self, event):
        noteIndex = event.data1 % 12 # Get the note
        octave = int(event.data1 / 12) # Get the octave

        whiteIndex = KEY_TO_POSITION[noteIndex] # Get the corresponding 
        blackOffset = 0
        if whiteIndex == -1: # If -1, we hit a back, get the precedent white and add an offset
            whiteIndex = KEY_TO_POSITION[noteIndex - 1]
            blackOffset = 1

        new_event_value = self.currentRoot + (self.currentScale[whiteIndex] + blackOffset) + 12*octave        
        
        # Edit the event
        event.data1 = new_event_value
