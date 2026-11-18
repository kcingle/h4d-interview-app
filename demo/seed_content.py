"""
demo/seed_content.py — Made-up content for the conference demo database.

EVERY person, unit, lab and event below is invented. The setting is
modeled on this team's problem area (GPS-denied navigation for a cavalry
unit) but nothing here comes from a real interview. Names were checked
against the real interviewee list so none of them matches a real person.

Transcripts use only straight quotes and plain punctuation, so the
verbatim quote check (ai._quote_appears_in_notes) has nothing to trip on.
"""

FICTIONAL_UNIT = "Thunder Squadron (fictional cavalry squadron)"

# (key, parent_key or None, statement) in tree order. Keys are local to
# this file; the seed script maps them to real hypothesis ids.
HYPOTHESES = [
    ("h1", None, "Scouts lose a reliable position fix within minutes of GPS jamming and fall back to map and compass."),
    ("h1a", "h1", "Navigation errors under jamming make spot reports late or wrong."),
    ("h1b", "h1", "Training in navigating without GPS has lapsed."),
    ("h2", None, "Leaders can't tell whether a reported position came from GPS or a fallback method."),
    ("h3", None, "Scouts would adopt a low-cost inertial or visual navigation aid only if it fits existing kit and needs no new training."),
]

SEED_INTERVIEWS = [
    {
        "key": "treadway",
        "person": {
            "name": "Marisol Treadway",
            "rank": "SSG",
            "role": "Scout section sergeant",
            "organization": FICTIONAL_UNIT,
            "seniority_level": "Mid-level NCO",
            "relationship": "beneficiary",
            "branch_service": "Army",
            "interview_date": "2026-10-20",
            "descriptor": "Fictional demo persona: scout section sergeant who navigated through a jammed night.",
            "interviewers": ["H4D demo team"],
        },
        "notes": "Spoke quickly and with a lot of specifics. Got visibly frustrated describing the gear that ended up in the connex. Offered the introduction to her troop commander without being asked.",
        "answers": [
            "She was very specific and confident about the jammed night and the 800 meter error. She got frustrated, not embarrassed, when talking about gear that ended up unused. Nothing important happened off the transcript.",
            "The one concrete commitment was her offer to introduce us to her troop commander, which she made without being asked. She did not commit to testing anything or to any money.",
            "We did not dig into budget or who buys equipment beyond her saying it was above her pay grade. We plan to ask the troop commander about that.",
        ],
        "transcript": """Interviewer: Can you walk me through the last time your section lost GPS?
SSG Treadway: Sure. That was the rotation in September. We were screening forward of the squadron at night, three vehicles spread across about four kilometers. Around 0200 the receivers started showing position jumps. One minute I'm on the ridge, the next it says I'm two kilometers east in a valley. Then it just went to no fix.

Interviewer: How long did it take before you realized it was jamming and not a bad device?
SSG Treadway: Maybe ten minutes. Honestly that's the dangerous part. The first few minutes you trust the screen because you always trust the screen. My gunner said the tracker had us sitting in a lake. That's when I knew.

Interviewer: What did you do then?
SSG Treadway: We went old school. Map, protractor, compass, the odometer and terrain association. I had one soldier in the section who was actually good at it. One. The other two vehicle commanders had not done a real land nav lane since their leadership course.

Interviewer: When was the last time the section trained on navigation without GPS?
SSG Treadway: Formally? I'd say over a year ago. It gets cut first when the training calendar is full. Nobody gets evaluated on it at the qualification tables. We get evaluated on gunnery.

Interviewer: What happened with your reporting that night?
SSG Treadway: My first spot report after the jamming started was off by about 800 meters. I sent a grid for an enemy observation post that put it on the wrong side of a draw. The troop called it up to squadron. The fires cell almost planned on it before my second report corrected it. That correction took twenty five minutes because I had to move to get a better look and shoot an azimuth to two known points.

Interviewer: Did anybody higher up know your grid came from map and compass instead of GPS?
SSG Treadway: No. There's no way to tell them in the format. A grid is a grid. I said it over the radio once, but by the time it got typed into the system it was just ten digits. That's actually what bugs me most.

Interviewer: Would you use a device that gave you a position when GPS is jammed?
SSG Treadway: If it worked, yes. But we've been handed a lot of stuff.

Interviewer: Tell me about the last piece of gear you were handed.
SSG Treadway: Last year we got a new radio accessory. It needed its own battery type, its own charger, and a two day class. Half the section never took the class. By the second month it lived in a connex. So if your thing needs another battery or another class, it's going to live in the connex too.

Interviewer: What would it need to look like?
SSG Treadway: It has to run off what we already carry, show up on the screens we already look at, and work the first time without a class. And it has to tell me how sure it is. If it's guessing, I want to know it's guessing.

Interviewer: How much would your unit pay for something like that?
SSG Treadway: That's above my pay grade. I can tell you my troop commander would want to see it. I'll introduce you to him, he's been fighting this exact problem with the squadron staff.

Interviewer: Is there anything else we should have asked?
SSG Treadway: Ask about the night after. The second night we planned for jamming from the start and we were fine. We moved slower, but every grid was right. So it's not that we can't do it. It's that nobody practices it until it happens.
""",
    },
    {
        "key": "okafor",
        "person": {
            "name": "Desmond Okafor",
            "rank": "CPT",
            "role": "Cavalry troop commander",
            "organization": FICTIONAL_UNIT,
            "seniority_level": "Company-grade officer",
            "relationship": "beneficiary",
            "branch_service": "Army",
            "interview_date": "2026-10-24",
            "descriptor": "Fictional demo persona: troop commander who built his own workaround for marking unreliable grids.",
            "interviewers": ["H4D demo team"],
        },
        "notes": "Calm and analytical. Drew the reporting chain on a whiteboard while talking. Was skeptical of tools in general after the laptop app experience.",
        "answers": [
            "He was calm and analytical, and skeptical of new tools after the laptop app failed. He was most animated when describing the code word workaround his troop invented.",
            "He committed to setting up an interview with his EW technician this week. He did not commit to any purchase, but said a motor pool demo with his S6 present would get his attention.",
            "We did not ask how the squadron currently records where a grid came from at higher levels. That is a gap for our next interview with the squadron S3.",
        ],
        "transcript": """Interviewer: What's your role in the troop when jamming starts?
CPT Okafor: I own the picture for the troop. Three platoons out front, and I'm feeding squadron. When jamming starts, my job turns into figuring out which reports I can trust.

Interviewer: How do you decide which reports to trust?
CPT Okafor: Mostly I know my people. If an experienced section sergeant sends a grid, I trust it. If a new lieutenant sends one, I ask him how he got it. But that's in my head, not in any system. When I hand the picture to squadron, all that context is gone. They see icons.

Interviewer: Can you give me an example from the last rotation?
CPT Okafor: In September one of my sections sent a grid that was about 800 meters off. It nearly turned into a fire mission. The grid itself wasn't the main issue though. The bigger delay was the relay. It took almost forty minutes from the scout seeing it to squadron acting on it, and most of that was the report bouncing between nets because the digital system was down too.

Interviewer: So the navigation error wasn't the main cause of the delay?
CPT Okafor: Not the main cause. The bad grid hurt, but the forty minutes was mostly relay and battle tracking. I'd split it maybe a third navigation, two thirds everything else.

Interviewer: How do you track where your own platoons are when GPS is down?
CPT Okafor: Paper map and a grease pencil. Every thirty minutes I make them send a position with how they got it. We made up a code word for that ourselves. Ground truth means map and terrain, box means the GPS. It's not in any manual. We just did it after the first night.

Interviewer: Does squadron know about that code?
CPT Okafor: The S3 knows because I told him. It doesn't go into the system. It dies at the troop command post.

Interviewer: Have you tried any tools to fix this?
CPT Okafor: We tried a laptop app a contractor showed us at a training event. It looked great in the demo. In the field it needed a network connection to load the maps and we didn't have one. That was the end of that.

Interviewer: What would make you try something again?
CPT Okafor: A demo in our motor pool on our vehicles, not a conference room. And I'd want my S6 there, because if it touches the network he can kill it.

Interviewer: Who else should we talk to?
CPT Okafor: Talk to our EW technician, Chief Vasquez-Hart. She can tell you what the jamming actually looks like, because what we think is happening and what's happening aren't always the same thing. I can set that up this week.

Interviewer: Anything we didn't ask?
CPT Okafor: Don't assume the problem is only the device. The problem is the trust chain. Somebody needs to know where a grid came from.
""",
    },
    {
        "key": "vasquez_hart",
        "person": {
            "name": "Lena Vasquez-Hart",
            "rank": "CW3",
            "role": "Electronic warfare technician",
            "organization": FICTIONAL_UNIT,
            "seniority_level": "Senior warrant officer",
            "relationship": "adjacent",
            "branch_service": "Army",
            "interview_date": "2026-10-29",
            "descriptor": "Fictional demo persona: EW technician who logged the jamming and spoofing during the rotation.",
            "interviewers": ["H4D demo team"],
        },
        "notes": "Very precise, corrected our terminology twice. Firm about the emissions point, it was clearly a hard requirement for her.",
        "answers": [
            "She was precise and corrected our terminology twice. The point about devices that transmit was clearly a hard requirement for her, not a preference.",
            "She offered to share her own detection timelines if we send a written request through the troop. Nothing else was committed.",
            "We did not ask how often spoofing, as opposed to jamming, has shown up across rotations. That is worth a follow up.",
        ],
        "transcript": """Interviewer: What does jamming actually look like from your seat?
CW3 Vasquez-Hart: People picture a switch that turns GPS off. It's rarely that. What we saw in September was intermittent. Ten minutes on, a few minutes off, sometimes only in certain valleys. Receivers would lose lock, get it back, lose it again.

Interviewer: How does that affect the scouts?
CW3 Vasquez-Hart: Intermittent is worse than total. When it's total, everybody knows to go to map and compass. When it's intermittent, the receiver keeps giving you a position, and some of those positions are bad. Soldiers trust the last fix they had.

Interviewer: Did you see any spoofing?
CW3 Vasquez-Hart: We saw signs of it on one night. Positions drifting in a straight line at a steady speed while the vehicle was parked. That's worse than jamming, because the screen looks healthy.

Interviewer: How long after jamming starts do units usually notice?
CW3 Vasquez-Hart: From what I logged, between five and fifteen minutes, depending on the crew. The experienced crews noticed fast because they compare the screen to the terrain out of habit. Newer crews noticed when something obviously broke, like an icon in a lake.

Interviewer: Is there a way for you to warn the scouts in real time?
CW3 Vasquez-Hart: I can detect it and report it up. Getting that warning down to a scout vehicle in time is the hard part. By the time my report gets to the troop, they've usually already figured it out on their own.

Interviewer: Would an inertial device solve this?
CW3 Vasquez-Hart: It helps with the first part, keeping a position when the signal goes away. It doesn't help if the device keeps believing a spoofed signal. Whatever you build has to be able to say, I don't trust the GPS right now, and stop using it.

Interviewer: What would you want such a device to tell the user?
CW3 Vasquez-Hart: Two things. Where it thinks you are, and how it knows. A confidence number alone won't mean anything to a nineteen year old at night. Something like GPS suspect, using inertial for the last twelve minutes, would.

Interviewer: Anything else?
CW3 Vasquez-Hart: Yes. Please don't build something that transmits. Anything that transmits is something I have to worry about getting found. Passive is the only thing I'd sign off on.
""",
    },
    {
        "key": "marsh",
        "person": {
            "name": "Elliot Marsh",
            "rank": "",
            "role": "Navigation researcher (inertial and visual navigation)",
            "organization": "Northfield Applied Navigation Lab (fictional)",
            "seniority_level": "Principal investigator",
            "relationship": "expert",
            "branch_service": "Civilian",
            "interview_date": "2026-11-05",
            "descriptor": "Fictional demo persona: civilian researcher on navigation without satellite signals.",
            "interviewers": ["H4D demo team"],
        },
        "notes": "Generous with numbers but careful to say they were his lab's results, not guarantees. Laughed about the cables and power problems.",
        "answers": [
            "He was careful to present his numbers as his own lab's test results, not guarantees, and he encouraged us to measure in the field ourselves.",
            "He offered to share the test procedure his lab uses for measuring drift. No commitment beyond that.",
            "We did not ask which units or programs have funded his research contracts. That could point us to who owns the budget.",
        ],
        "transcript": """Interviewer: What does your lab work on?
Dr. Marsh: Navigation when satellite signals are unavailable. Mostly inertial sensors combined with other cues, like vision, odometry and terrain matching.

Interviewer: How well does a low-cost inertial unit hold position on its own?
Dr. Marsh: Not well. The cheap MEMS units in phones and small devices drift fast. On their own you can be hundreds of meters off within a few minutes, and kilometers off in an hour. The units that hold position for hours are expensive, heavy, and often export controlled.

Interviewer: So a cheap inertial device wouldn't help scouts?
Dr. Marsh: On its own, no. Combined with the vehicle odometer and a camera, much better. With odometry we've seen errors around one to two percent of distance traveled in our tests. So after ten kilometers, maybe 100 to 200 meters. That's useful for a scout, but it's not GPS.

Interviewer: Is 100 to 200 meters good enough?
Dr. Marsh: You'd have to ask them. For calling fires, probably not without a correction. For knowing which side of a ridge you're on, yes. The honest answer is it depends on the task, and the device should tell the user which tasks it's good enough for.

Interviewer: What's the hardest part of getting this into the field?
Dr. Marsh: Integration, not the algorithm. Every vehicle has different mounts, power and displays. Our prototypes work on the bench. The last field test we did, half our problems were cables and power.

Interviewer: Have military units bought anything from your lab?
Dr. Marsh: We've had a lot of interest and a few small research contracts. Nobody has bought a fielded product. The pattern we see is excitement at demos and then a long silence when it's time to find money for it.

Interviewer: What would you tell a student team going after this problem?
Dr. Marsh: Find out who owns the budget before you build anything. And measure the error in the field yourselves, don't trust anybody's spec sheet, including mine.
""",
    },
]

# The live interview the presenter processes on stage. Same text as
# demo/DEMO_TRANSCRIPT.txt (the file the guide tells the presenter to copy).
LIVE_PERSON = {
    "name": "Jordan Vance",
    "rank": "1LT",
    "role": "Scout platoon leader",
}

# Three general answers that fit whatever the clarifying questions turn
# out to be. Used by rehearsals and printed in the instructor guide.
LIVE_ANSWERS = [
    "He was open and a little embarrassed when he admitted the kilometer error on his own report. He was most confident when talking about the monthly navigation lane, and he looked frustrated when talking about devices that need a personal phone.",
    "The one concrete commitment was his offer to test a device with his platoon and write up the results. He did not commit to any purchase, and he said the buying decision sits with the squadron S3 and S6 and with brigade.",
    "We did not ask how often the platoon has lost GPS outside of training center rotations, or what the troop commander did differently once he knew a grid came from a map. Those are next questions for the troop commander.",
]
