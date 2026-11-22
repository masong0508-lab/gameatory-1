"""Payback: Stunt Fox - the expansion pack's renames (English text only)."""

TITLE = 'Payback: Stunt Fox'

EXACT = {
    'Play game': 'Play STUNT FOX',
    'Play single player game': 'Stunt Fox story',
    'Single player rampage': 'Stunt Fox free roam',
    'RAMPAGE SETUP': 'FREE ROAM SETUP',
    'Welcome to %s. Prepare to rampage!':
        'Welcome to %s. The stadium has jumps, dash plates and speed loops. '
        'In a car, SELECT+START retries at the stadium. Hold SELECT to build. '
        'Keep accelerating through the loop!',
    'Welcome to Payback. Your target score for this level is 1,500,000 points. '
    'Answer the phones to get missions. Good luck.':
        'Welcome to Payback: Stunt Fox! Find the stadium for jumps, dash plates and loops. '
        'Hold SELECT to build. Your target is 1,500,000 points. Answer phones for missions.',
    'Helicopter': 'Arwing',
    'Pug Racer': 'Blue Falcon',
    'a Pug Racer': 'the Blue Falcon',
    'Rocket car': 'Fire Stingray',
    'A new city has been unlocked!': 'A new Stunt Fox city has been unlocked!',
}

# city names the level data points at directly (all languages share them)
INPLACE = {'1. Freedom City': '1. Mute City', '2. Los Francos City': '2. Big Blue City'}

REPLACE = [
    ('Freedom City', 'Mute City'),
    ('Los Francos', 'Big Blue'),
    ('Corona City', 'Corneria'),
]
