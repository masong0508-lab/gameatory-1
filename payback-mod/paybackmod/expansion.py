"""Payback: Stunt Fox - the expansion pack's renames (English text only)."""

TITLE = 'Payback: Stunt Fox'

EXACT = {
    'Play game': 'Play STUNT FOX',
    'Play single player game': 'Stunt Fox story',
    'Single player rampage': 'Stunt Fox free roam',
    'RAMPAGE SETUP': 'FREE ROAM SETUP',
    'Welcome to %s. Prepare to rampage!':
        'Welcome to %s. Gravity is low, the streets have ramps and the stadium is a stunt park. '
        'Hold SELECT to build: A ramp, B block, R raise, L clear.',
    'Welcome to Payback. Your target score for this level is 1,500,000 points. '
    'Answer the phones to get missions. Good luck.':
        'Welcome to Payback: Stunt Fox! Gravity is low, the streets have ramps and the stadium is a '
        'stunt park. Hold SELECT to build: A ramp, B block, R raise, L clear. Your target score is '
        '1,500,000 points. Answer the phones to get missions.',
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
