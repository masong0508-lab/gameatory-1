"""Fox Station's blob (stage 2, S): the rooms (tools/content/stgeo.py), the crew's talk and the messages, as station.c reads
them straight from the ROM. s2build.py links it as st_blob; with no builder it is 8 zero bytes and the station is off.

    python3 tools/content/station.py [--list] [--out file]      the talk's numbers, and the blob's size

Layout (little-endian, every table 4-aligned, offsets from the blob's start, no pointers):
    StHead  40 bytes: magic 'STN1', ver, nroom, nnode, nent, ntext, pad, off_room, off_node, off_ent, off_text, size, crc32
    StRoom  48 bytes each, nroom of them (room 0, the hangar, is all zeros: it is the old docked view)
    ... each room's parts (StPart 16 bytes: nv, nf, off_v, off_f, off_n), vertices, faces, normals, boxes, cameras,
        uses, crew
    StNode   8 bytes: {u8 speaker, flags; u16 text; u16 next; u8 cond, act}
    StEnt    8 bytes: {u8 crew, cond, flags, pad; u16 node, id}   (id is what the mission engine's `talk CREW ID` waits for)
    text: u16 offsets (ntext of them) from the table's start, then NUL-terminated ASCII in the Stunt Fox font (id 0 is "")

A conversation is an entry (a crew member, a condition, and its first node); its nodes chain by `next` (0 ends it) and the
end raises s2_ev(EV_TALK, crew, id). The crew's first unheard entry whose condition holds is the one they say; when all
are heard they chatter (the REPEAT entries, in turn). Conditions (cond): 0 always; 0x10 + k chapter k open; 0x30 + k chapter k's
acts all done; 0x50 + f campaign flag f; 0x58 + u unlock u; 0x60 Ace mode; bit 7 the opposite. Acts (act): low 3 bits the
operation (1 unlock, 2 set flag, 3 start contract, 4 open a terminal), the rest its argument.
"""
import os
import re
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stgeo as G                                   # noqa: E402

MAGIC = 0x314e5453                                  # 'STN1'
VER = 1
LINE_MAX, LINES_MAX = 36, 2                         # letters a line, lines a node (the dialogue panel)
E_REPEAT, E_MSG, E_LOG = 1, 2, 4
A_UNLOCK, A_SET, A_START, A_OPEN = 1, 2, 3, 4

CH = lambda k: 0x10 + k                             # chapter k is open
DONE = lambda k: 0x30 + k                           # chapter k is done
FLAG = lambda f: 0x50 + f                           # campaign flag f (campaign.h CP_FLAG_*)
UNLOCK = lambda u: 0x58 + u                         # unlock u (CP_UNLOCK_*)
ACE = 0x60
NOT = lambda c: 0x80 | c
SET = lambda f: A_SET | f << 3                       # an act: campaign flag f
KESTREL_FLAG, FINALE_FLAG = 1, 2                    # content/campaign.sfc's FLAG_*

R, P, N, D, Q, J, K, S = (G.CREW[n] for n in ('ROOK', 'PIP', 'NOVA', 'DUSTY', 'QUILL', 'JUNO', 'KESTREL', 'SABLE'))
OPEN = lambda t: A_OPEN | t << 3

# (crew, cond, flags, [lines of a node ... , or (line, act)]). Entry numbers are the order here, from 1: entry 1 is the one the first
# act's `talk rook 1` waits for.
TALK = [
    (R, 0, 0, ["VEX GRABBED A CORE AND RAN.\nGET TO THE ARWING. KEEP IT LOW.",
               "EVERY GATE ON THE MAP RUNS ON CORES.\nVEX WANTS ALL OF THEM.",
               "LOOK AROUND THE STATION FIRST.\nPIP HAS UPGRADES, NOVA HAS THE MAP."]),
    (P, 0, 0, ["HI FOX! I AM PIP. I KEEP THE ARWING\nIN ONE PIECE. MOSTLY ONE PIECE.",
               ("THE BENCH IS ON THE LEFT, THE PAINT\nRACK ON THE RIGHT. GO NUTS.", OPEN(G.T_SHOP))]),
    (N, 0, 0, ["I AM NOVA. THE TABLE SHOWS EVERY CITY\nWE HAVE OPENED.",
               ("STEP UP TO IT AND PICK ONE. THE\nSTATION FOLLOWS YOUR COURSE.", OPEN(G.T_MAP))]),
    (D, 0, 0, ["DUSTY. I DRIVE THINGS. FAST. WITH\nOPINIONS.",
               "TIP: FLIP A CAR OFF A RAMP AND THE\nPAY GOES UP. TRY IT."]),
    (Q, 0, 0, ["QUILL. I KEEP THE MEDALS. THERE ARE\nSEVENTY-TWO. ALL ARE EMPTY.",
               ("THAT WAS A JOKE. THE HALL FILLS AS\nYOU FLY. STEP UP TO SEE HOW FULL.", OPEN(G.T_TROPHY))]),
    (J, 0, 0, ["JUNO, COMMS. I SEND THE MESSAGES AND\nKEEP YOUR PROGRESS SAFE.",
               ("SAVE AT MY TERMINAL BEFORE A BIG\nFLIGHT. I WILL WAIT.", OPEN(G.T_COMMS))]),
    (R, CH(1), 0, ["VEX LEFT HER TEST GROUND OPEN. I TURNED\nIT INTO A TRAINING DISTRICT.",
                   "GO PRACTISE. EVERYTHING THERE IS\nFAIR GAME AND NOTHING IS REAL."]),
    (P, CH(1), 0, ["THE TRAINING DISTRICT IS HARD ON\nWINGS. I PATCHED YOURS TWICE."]),
    (N, CH(1), 0, ["KILLING ZONE IS ON THE TABLE NOW.\nIT IS SMALL. IT IS ANGRY."]),
    (R, CH(2), 0, ["THE PIRATES PAY IN GOLD. WE PAY IN\nBROKEN CARS AND BRUISED ROOFTOPS.",
                   "KEEP THE CIVILIANS CLEAR. I MEAN IT."]),
    (D, CH(2), 0, ["HOLD SELECT FOR HALF A SECOND AND THE\nARWING COMES TO YOU. ANYWHERE."]),
    (P, CH(2), 0, ["LOS FRANCOS FOLK LEAVE US PARTS ON\nTHE ROOF. THEY CALL IT TIPPING."]),
    (Q, CH(2), 0, ["A GOOD MEDAL IS A SMALL MEDAL IN A\nHARD PLACE."]),
    (R, CH(3), 0, ["THE MONEY MEN LIVE UP HIGH. GOOD\nTHING WE FLY.",
                   "WATCH THE EL TRAINS. THEY DO NOT\nSTOP FOR FOXES."]),
    (N, CH(3), 0, ["LITTLE CHICAGO SITS ON A GRID. TALL\nTOWERS, NARROW GAPS. FLY STRAIGHT."]),
    (D, CH(3), 0, ["THE EL TRAINS ARE SOLID. THE PIRATES\nARE NOT. AIM ACCORDINGLY."]),
    (J, CH(3), 0, ["THE CODE ON MY SCREEN BRINGS YOU BACK\nANYWHERE. WRITE IT DOWN."]),
    (P, CH(4), 0, ["THE WOODS WORKSHOP HAS A LATHE I WANT.\nCAN YOU BORROW IT? KIDDING. MOSTLY."]),
    (Q, CH(4), 0, ["BEST TIMES GO ON THE SECOND PAGE. THE\nWORST GO IN A DRAWER. MINE."]),
    (R, CH(5), 0, ["THE CORES SLEEP IN A HARBOUR FORT.\nWE ARE NOT KNOCKING."]),
    (N, CH(5), 0, ["CORONA'S HARBOUR HAS FOG ON THE TABLE.\nTRUST THE MARKERS, NOT YOUR EYES."]),
    (D, CH(5), 0, ["SWIM! IT TURNS OUT FOXES SWIM. LOW\nBANKS AND LADDERS GET YOU OUT."]),
    (P, CH(6), 0, ["BIG TRACK IS RIGGED, SO I BUILT A\nSTRONGER ENGINE. THE SLOT IS OPEN."]),
    (N, CH(6), 0, ["BIG TRACK: A LOOP WITH FOUR GATES AND\nONE LIAR. WATCH THE LIAR."]),
    (Q, CH(6), 0, ["A RACE MEDAL NEEDS A CLEAN LINE. A\nCLEAN LINE IS A TRUE LINE."]),
    (R, CH(7), 0, ["KESTREL FLEW YOUR LAP AGAIN LAST NIGHT.\nSHE ASKS WHICH SIDE YOU ARE ON."]),
    (D, CH(7), 0, ["SAND IN THE ENGINE. SAND IN MY LUNCH.\nSAND IN THE LOUNGE. HELP."]),
    (J, CH(7), 0, ["KESTREL KEEPS CALLING THE OLD CHANNEL.\nSHE SAYS SHE IS JUST CHECKING."]),
    (R, FLAG(KESTREL_FLAG), 0, ["KESTREL IS WITH US NOW. GIVE HER ROOM.\nSHE HAS EARNED THE QUARTERS."]),
    (J, FLAG(KESTREL_FLAG), 0, ["KESTREL'S CALL SIGN IS ON OUR LIST NOW.\nSHE SAYS IT SOUNDS BETTER THAN HERS."]),
    (K, 0, 0, ["SO YOU ARE THE FOX. I STILL HOLD THE\nCOAST LAP. FOR NOW.",
               "VEX PAID WELL. SHE ALSO SAID THE\nCORES POWER A HUNDRED GATES.",
               "THEY POWER ONE. THE LAST ONE. I\nHAVE SEEN IT. IT IS VERY BIG."]),
    (D, CH(8), 0, ["ROOK SAYS DO NOT PANIC. I SAY PANIC A\nLITTLE. IT KEEPS YOU SHARP."]),
    (P, CH(8), 0, ["TANKS! I LOVE TANKS. DO NOT TELL ROOK."]),
    (R, CH(9), 0, ["LAST CORES. UNDER A PARK. OF ALL\nPLACES.", "BRING THEM HOME, FOX."]),
    (N, CH(9), 0, ["REAL PARK HAS A PICNIC ZONE. DO NOT\nLAND ON THE PICNIC."]),
    (Q, CH(9), 0, ["NEARLY EVERYTHING IS ON THE WALL. WHAT\nIS MISSING IS ALWAYS THE ONE IN A TREE."]),
    (K, CH(9), 0, ["THE LAST GATE OPENS TO WHERE VEX CAME\nFROM. I WANT TO KNOW WHAT SHE LEFT."]),
    (R, CH(10), 0, ["THE GATE IS LIT. END THIS, FOX.\nTHEN COME HOME."]),
    (N, CH(10), 0, ["THE LAST COURSE IS PLOTTED. IT ENDS AT\nA GATE. I HAVE NO FURTHER ADVICE."]),
    (D, CH(10), 0, ["I PUT A BET ON YOU. DO NOT TELL\nANYONE. ESPECIALLY NOT ROOK."]),
    (P, CH(10), 0, ["EVERY BOLT IS TIGHT. GO BE BRILLIANT."]),
    (J, CH(10), 0, ["EVERY CHANNEL IS QUIET. THAT MEANS\nEVERYONE IS LISTENING."]),
    (R, FLAG(FINALE_FLAG), 0, ["THE GATE IS DARK AND THE CORES ARE\nHOME. NICE FLYING, FOX.",
                               "IF YOU WANT A HARDER SKY, ACE MODE\nIS NOW ON. THE PIRATES FLY BETTER."]),
    (Q, FLAG(FINALE_FLAG), 0, ["THE HALL HAS A NEW PLAQUE. IT SAYS YOUR\nNAME. I SPELLED IT RIGHT."]),
    (K, FLAG(FINALE_FLAG), 0, ["YOU WON. I HATE THAT. I ALSO LIKE IT.",
                               "ACE MODE IS YOURS. COME FIND ME IN\nIT. I WILL BE FASTER."]),
    # the station's own story (a chapter done): each sets a campaign flag (3..7) that opens the next option
    (R, DONE(2), 0, ["LOS FRANCOS IS QUIET AND THE ROOFS ARE OURS.",
                     "THE CITIES KEEP ASKING FOR HELP. SO I WROTE THEM A BOARD.",
                     ("IT IS ON THE CONTRACTS SCREEN: PRESS RIGHT. ONE JOB A CITY, AND A BONUS ON TOP.", SET(3))]),
    (P, DONE(4), 0, ["WOODS FOLK PAID IN TIMBER AND TIPS. I TURNED\nTHE TIPS INTO A JAR.",
                     ("THE JAR ADDS FIFTY CREDITS TO EVERY CITY BONUS. SAY THANKS TO THE TREES.", SET(4))]),
    (N, DONE(6), 0, ["BIG TRACK LOOPS BACK ON ITSELF. SO DOES MONEY.",
                     ("I FOUND ROUTE FEES IN THE TABLE. FIFTY MORE ON EVERY CITY BONUS.", SET(5))]),
    (K, DONE(7), 0, ["THE DESERT IS DONE. I HUNG A BOARD BY THE DESK.",
                     "THREE LAPS I STILL OWN. TWO ARE OPEN TO YOU NOW.",
                     ("PRESS RIGHT ON MY LOG. BEAT THEM AND I PAY. WIN THE FINALE AND I PAY MORE.", SET(6))]),
    (R, DONE(8), 0, ["THE TANKS ARE QUIET. KESTREL ASKED ME TO PASS ON ONE THING.",
                     ("SHE HUNG A THIRD LAP ON HER BOARD. THE HARD ONE. GOOD LUCK.", SET(7))]),
    (S, CH(2), 0, ["I LEARNED THE ROOFS IN LOS FRANCOS.",
                   "I RAN THEM AS A KIT. THE CITY WAS KIND TO A FAST FOX.",
                   "NOW I RUN ERRANDS FOR THE CREW. THE ROOFS DO NOT MIND."]),
    # chatter: said in turn once the rest is heard
    (R, 0, E_REPEAT, ["CHECK THE BOARD. CONTRACTS PAY WELL."]),
    (R, 0, E_REPEAT, ["FLY LOW OVER A CITY, HIGH IN SPACE.\nNEVER THE OTHER WAY ROUND."]),
    (R, 0, E_REPEAT, ["A GOOD PILOT COMES BACK. BE GOOD."]),
    (R, 0, E_REPEAT, ["NO FREE FLIGHTS. EVERY TRIP HAS A JOB."]),
    (P, 0, E_REPEAT, ["ENGINE, LASERS, SHIELD, RACK. FOUR\nTHINGS TO BRAG ABOUT."]),
    (P, 0, E_REPEAT, ["I ADDED A COLOUR. IT IS CALLED TEAL.\nIT WAS ALREADY TEAL."]),
    (P, 0, E_REPEAT, ["A CLEAN SHIP IS A FAST SHIP. I MADE\nTHAT UP, BUT IT FEELS TRUE."]),
    (P, 0, E_REPEAT, ["OIL IS NOT A PERSONALITY. I LEARNED\nTHAT THE HARD WAY."]),
    (N, 0, E_REPEAT, ["THE TABLE KEEPS EVERY ACT YOU HAVE\nDONE. THE DOTS GO GREEN."]),
    (N, 0, E_REPEAT, ["EACH CITY SITS UNDER THE STATION IN\nTURN. WE ORBIT. YOU TRAVEL."]),
    (N, 0, E_REPEAT, ["A GOOD COURSE IS A SHORT COURSE."]),
    (N, 0, E_REPEAT, ["HOLD SELECT NEAR THE STATION IN\nSPACE AND THE BAY DOORS OPEN."]),
    (D, 0, E_REPEAT, ["R FIRES LASERS. L FIRES MISSILES. THE\nRACK HOLDS ONLY SO MANY."]),
    (D, 0, E_REPEAT, ["IN SPACE THE STICK CLIMBS OR DIVES.\nOPTIONS HAS AN INVERT SWITCH."]),
    (D, 0, E_REPEAT, ["BAIL OUT IN SPACE WITH A JET PACK AND\nFLOAT. IT IS EXTREMELY FUN."]),
    (D, 0, E_REPEAT, ["THE MEDALS ARE HIDDEN. LOOK UP. THEN\nLOOK UP MORE."]),
    (D, 0, E_REPEAT, ["A LANDING IS A BUMP YOU WALK AWAY\nFROM. KEEP THE GEAR DOWN."]),
    (D, 0, E_REPEAT, ["LOOPS ARE GOOD FOR POINTS AND BAD FOR\nLUNCH."]),
    (Q, 0, E_REPEAT, ["THE CITY'S OWN TROPHIES ARE ON THE\nLAST PAGE. THEY KEEP THEIR OWN SCORE."]),
    (Q, 0, E_REPEAT, ["SEVENTY-TWO MEDALS. I HAVE COUNTED\nTHEM TWICE. THEY KEEP MOVING."]),
    (Q, 0, E_REPEAT, ["DO NOT TOUCH THE PLINTHS. THEY ARE\nSTILL WARM FROM THE LAST WINNER."]),
    (J, 0, E_REPEAT, ["A SAVE IS A PROMISE TO YOURSELF. KEEP\nIT OFTEN."]),
    (J, 0, E_REPEAT, ["THE MESSAGES TERMINAL IS ON THE LEFT.\nTHE GOOD NEWS IS ON TOP."]),
    (J, 0, E_REPEAT, ["I CAN HEAR THE CITIES FROM HERE. THEY\nSOUND BUSY."]),
    (K, 0, E_REPEAT, ["ACE MODE MAKES THE PIRATES TOUGHER AND\nTHE PARS TIGHTER. LIKE ME."]),
    (K, 0, E_REPEAT, ["DO NOT LOOK AT THE BUNK. IT IS NOT\nMADE. I WAS UP EARLY."]),
    (D, 0, E_REPEAT, ["THE COUCH IS LUMPY. THE LUMPS ARE\nMINE. I EARNED THEM."]),
    (D, 0, E_REPEAT, ["WANT TO KNOW HOW TO FLIP A CAR?\nGO FAST, HIT A RAMP, HOLD A DIRECTION."]),
    # the terminal for messages (Comms) and the log in the quarters
    (J, 0, E_MSG, ["WELCOME ABOARD, FOX.\nALL CHANNELS ARE OPEN."]),
    (R, 0, E_MSG, ["CONTRACTS ARE ON THE OPS BOARD.\nTAKE ONE FOR THE CREDITS."]),
    (P, CH(1), E_MSG, ["THERE IS PAINT IN THE RACK FOR GOOD\nFLYING. ASK ME. -PIP"]),
    (N, CH(3), E_MSG, ["THE TABLE SHOWS FOUR CITIES NOW.\nI LIKE THE ROUND ONES. -NOVA"]),
    (D, CH(5), E_MSG, ["SWIMMING LESSONS IN THE LOUNGE\nTONIGHT. BRING A TOWEL. -DUSTY"]),
    (Q, CH(6), E_MSG, ["A NEW SHELF IS UP. IT IS EMPTY.\nYOU KNOW WHAT TO DO. -QUILL"]),
    (K, CH(7), E_MSG, ["YOUR LAP WAS CLOSE. COME AND TALK.\nCALL SIGN KESTREL."]),
    (J, FLAG(KESTREL_FLAG), E_MSG, ["KESTREL JOINED THE CREW. THE QUARTERS\nARE OPEN. -JUNO"]),
    (R, CH(10), E_MSG, ["THE LAST GATE. I WILL BE AT THE BOARD.\nCOME HOME. -ROOK"]),
    (J, FLAG(FINALE_FLAG), E_MSG, ["EVERY CHANNEL IS SINGING. NICE WORK,\nFOX. -JUNO"]),
    (K, 0, E_LOG, ["LOG 1. I FLEW FOR VEX FOR TWO YEARS.\nTHE MONEY WAS GOOD. THE SKY BETTER."]),
    (K, 0, E_LOG, ["LOG 2. I SET FIVE LAPS NOBODY BEAT.\nTHEN A FOX FLEW THEM FASTER."]),
    (K, CH(9), E_LOG, ["LOG 3. VEX KEEPS A LOCKED HANGAR. IT\nHOLDS ONE SHIP. I NEVER SAW IT FLY."]),
    (K, CH(10), E_LOG, ["LOG 4. THE GATE IS NOT A WEAPON. IT IS\nA DOOR. I WANT TO KNOW WHERE IT GOES."]),
    (K, FLAG(FINALE_FLAG), E_LOG, ["LOG 5. IT WENT HOME. HER HOME. SHE WAS\nNOT A VILLAIN. SHE WAS LATE."]),
    (K, ACE, E_LOG, ["ACE LOG. THE PIRATES FLY HARDER NOW.\nSO DO I. FIND ME IN THE SKY."]),
    # Sable's talk (the ground liaison in the hub): a repeat, so it is said in full each time and never counted as heard
    (S, 0, E_REPEAT, ["HI FOX. I AM SABLE. I WALK THE CITIES FOR THE CREW.",
                      "THE CITIES TRUST A FACE THEY CAN READ. MINE HAS EARS.",
                      "MY EARS HEAR THE TRAFFIC. MY TAIL TELLS YOU I AM HAPPY.",
                      "IF A CITY SAYS NO, ASK ME. I WILL ASK AGAIN, POLITELY.",
                      "THE LIAISON DESK IS HERE IN THE HUB. I AM HERE MOST DAYS.",
                      "THE SNACKS ARE IN THE LOUNGE. DUSTY SAYS THEY ARE HIS.",
                      "GOOD FLYING OUT THERE. COME BACK WITH STORIES, FOX."]),
]

# characters the font has (draw2d.c: ASCII 32..95, lower case drawn as upper) and what the station never says
FONT_OK = set(chr(c) for c in range(32, 96))
BANNED = re.compile(r'\b(kill\w*|die\w*|dead|death|crime\w*|arrest\w*|murder\w*|bust\w*|wanted|cop|cops|police|slay\w*)\b', re.I)


def wrap(t):
    """The words as lines of at most LINE_MAX letters (the author's own line breaks are only spaces)."""
    words, lines, cur = t.replace('\n', ' ').split(), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > LINE_MAX:
            lines.append(cur)
            cur = w
        else:
            cur = cur + ' ' + w if cur else w
    lines.append(cur)
    return lines


def check_text(t, where):
    lines = t.split('\n')
    assert 1 <= len(lines) <= LINES_MAX, '%s: %d lines: %r' % (where, len(lines), t)
    for l in lines:
        assert len(l) <= LINE_MAX, '%s: line over %d letters: %r' % (where, LINE_MAX, l)
    assert set(t.replace('\n', ' ')) <= FONT_OK, '%s: a letter the font lacks: %r' % (where, sorted(set(t) - FONT_OK))
    assert not BANNED.search(t.replace('KILLING ZONE', 'THE ZONE')), '%s: %r' % (where, t)   # (a city's own name stays)


class Pool:
    def __init__(self):
        self.s, self.at = [''], {'': 0}

    def add(self, t):
        if t not in self.at:
            self.at[t] = len(self.s)
            self.s.append(t)
        return self.at[t]

    def pack(self):
        n = len(self.s)
        body = b''.join(s.encode('ascii') + b'\0' for s in self.s)
        offs, o = [], 2 * n
        for s in self.s:
            offs.append(o)
            o += len(s) + 1
        return struct.pack('<%dH' % n, *offs) + body


def pad4(b):
    return b + bytes(-len(b) % 4)


FUR_LIMIT = 24                                   # the crew model budget: vertices per crew model (design 7.3)


def fur_box(x0, x1, y0, y1, z0, z1, mat):
    """One box as traffic.c's person boxes: 8 vertices (bottom then top), 5 faces (no bottom); each face's normal points out."""
    vs = [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
    c = [sum(p[i] for p in vs) / 8.0 for i in range(3)]
    fs = []
    for q in quads:
        p0, p1, p2 = vs[q[0]], vs[q[1]], vs[q[2]]
        a = [p1[i] - p0[i] for i in range(3)]
        b = [p2[i] - p0[i] for i in range(3)]
        n = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
        m = sum(v * v for v in n) ** 0.5 or 1.0
        n = [v / m for v in n]
        f = [sum(vs[i][k] for i in q) / 4.0 - c[k] for k in range(3)]
        if sum(n[k] * f[k] for k in range(3)) < 0:
            n = [-v for v in n]
        fs.append((4, mat, 0, list(q), tuple(n)))
    return vs, fs


def fur_parts(crew_list):
    """The fur of each furry crew: a part in the crew's own frame (the head is at y 184..226, the hips at y 98), in the
    body colour (the ears and tail) or cream (the muzzle), so person() draws it with the body it sits on."""
    out = []
    for (c, x, z, yaw, model, body_m, legs, fur) in crew_list:
        if not fur:
            continue
        assert fur < 8, 'fur mask %d' % fur
        boxes = []
        if fur & G.FUR_EARS:
            boxes += [(-20, -4, 226, 266, -12, 12, G.M_CREAM), (4, 20, 226, 266, -12, 12, G.M_CREAM)]
        if fur & G.FUR_TAIL:
            boxes += [(14, 40, 52, 96, -10, 10, G.M_STUNT)]
        if fur & G.FUR_MUZZLE:
            boxes += [(-13, 13, 172, 200, 16, 34, G.M_CREAM)]
        vs, fs = [], []
        for bx in boxes:
            v2, f2 = fur_box(*bx)
            o = len(vs)
            vs += v2
            fs += [(n, mat, fl, [i + o for i in idx], nr) for (n, mat, fl, idx, nr) in f2]
        assert len(vs) <= FUR_LIMIT, 'crew %d: %d fur vertices' % (c, len(vs))
        out.append((vs, fs))
    return out


def pack_room(r, pool, start):
    """One room's data, to sit at `start` in the blob: the parts' vertices, faces and normals, their records, the boxes, cameras,
    uses and crew; -> (bytes, the StRoom record)."""
    geo, recs = bytearray(), bytearray()
    prs = []
    furs = fur_parts(r.crew)                          # after the room's own parts: not drawn with them (nparts counts those only)
    for vs, fs in list(r.mesh.parts) + furs:
        ov = len(geo)
        for (x, y, z) in vs:
            geo += struct.pack('<3h', x, y, z)
        geo = bytearray(pad4(bytes(geo)))
        of = len(geo)
        for (n, mat, fl, idx, nrm) in fs:
            geo += struct.pack('<9B', n, mat, fl, *(idx + [0] * (6 - n)))
        geo = bytearray(pad4(bytes(geo)))
        on = len(geo)
        for (n, mat, fl, idx, nrm) in fs:
            geo += struct.pack('<3h', *(max(-16384, min(16384, int(round(c * 16384)))) for c in nrm))
        geo = bytearray(pad4(bytes(geo)))
        prs.append((len(vs), len(fs), ov, of, on))
    for (nv, nf, ov, of, on) in prs:
        recs += struct.pack('<BBHIII', nv, nf, 0, start + ov, start + of, start + on)
    parts_at = start + len(geo)
    extra = bytearray()
    box_at = parts_at + len(recs)
    for (x0, z0, x1, z1) in r.mesh.boxes:
        extra += struct.pack('<4h', x0, z0, x1, z1)
    cam_at = box_at + len(extra)
    for c in r.cams:
        extra += struct.pack('<10h', *c, 0)
    use_at = box_at + len(extra)
    for (kind, arg, x, z, rad, sx, sz, label, ly, fl) in r.uses:
        extra += struct.pack('<4hBBBBhH', x, z, sx, sz, rad // 4, kind, arg, fl, ly, pool.add(label))
    crew_at = box_at + len(extra)
    k = 0
    for (c, x, z, yaw, model, body_m, legs, fur) in r.crew:
        assert c <= 8, 'crew %d: the crew field is 8 at most' % c
        fi = 0
        if fur:
            fi, k = k + 1, k + 1
        extra += struct.pack('<2hH4B2B', x, z, yaw & 0xffff, c, model, body_m, legs, fur, fi)
    data = pad4(bytes(geo) + bytes(recs) + bytes(extra))
    rr = struct.pack('<8BhhhH5I12x', len(r.mesh.parts), len(r.mesh.boxes), len(r.cams), len(r.uses), len(r.crew), r.ceil_c, r.floor_c, 0,
                     r.hx, r.hz, r.zmin, pool.add(r.title), parts_at, box_at, cam_at, use_at, crew_at)
    assert len(rr) == 48
    return data, rr


def pack(rooms=None):
    rooms = rooms or G.build_rooms()
    G.check(rooms)
    pool = Pool()
    nodes = [(0, 0, 0, 0, 0, 0)]                       # node 0: none
    ents = []
    for i, (crew, cond, flags, lines) in enumerate(TALK):
        assert i + 1 < 64 or flags & (E_REPEAT | E_MSG | E_LOG), 'entry %d: a story talk past 63 has no bit in the heard words' % (i + 1)
        first = len(nodes)
        pages = []                                     # a text of more than two lines goes on to a second node
        for ln in lines:
            text, act = ln if isinstance(ln, tuple) else (ln, 0)
            w = wrap(text)
            for k in range(0, len(w), LINES_MAX):
                pages.append(['\n'.join(w[k:k + LINES_MAX]), 0])
            pages[-1][1] = act
        for j, (text, act) in enumerate(pages):
            check_text(text, 'talk %d' % (i + 1))
            nodes.append((crew, 0, pool.add(text), first + j + 1 if j + 1 < len(pages) else 0, 0, act))
        ents.append((crew, cond, flags, first, i + 1))
    assert len(ents) < 255
    nroom, head_len = 9, 40
    base = head_len + nroom * 48
    blobs, recs = bytearray(), []
    for rid in range(nroom):
        r = rooms.get(rid)
        if r is None:
            recs.append(bytes(48))                      # the hangar: the old docked view
            continue
        data, rr = pack_room(r, pool, base + len(blobs))
        blobs += data
        recs.append(rr)
    node_b = b''.join(struct.pack('<2BHHBB', sp, fl, tx, nx, cd, ac) for (sp, fl, tx, nx, cd, ac) in nodes)
    ent_b = b''.join(struct.pack('<4BHH', cr, cd, fl, 0, nd, i) for (cr, cd, fl, nd, i) in ents)
    text_b = pool.pack()
    off_node = base + len(blobs)
    off_ent = off_node + len(node_b)
    off_text = off_ent + len(ent_b)
    size = off_text + len(text_b)
    out = bytearray(struct.pack('<IHHHHHHIIIIII', MAGIC, VER, nroom, len(nodes), len(ents), len(pool.s), 0, head_len, off_node, off_ent,
                                off_text, size, 0))
    assert len(out) == head_len, len(out)
    out += b''.join(recs) + blobs + node_b + ent_b + text_b
    assert len(out) == size, (len(out), size)
    out[head_len - 4:head_len] = struct.pack('<I', zlib.crc32(bytes(out[head_len:])) & 0xffffffff)
    return bytes(out)


def build(rom=None, orig=None, gen=None):
    """tools/s2build.py's hook: the blob for the link."""
    b = pack()
    print('station: %d bytes, %d talks, %d rooms' % (len(b), len(TALK), len(G.build_rooms())))
    return b


if __name__ == '__main__':
    b = pack()
    if '--list' in sys.argv:
        for i, (crew, cond, flags, lines) in enumerate(TALK):
            print('%3d %-7s cond %02x flags %d  %s' % (i + 1, [k for k, v in G.CREW.items() if v == crew][0], cond, flags,
                                                    (lines[0][0] if isinstance(lines[0], tuple) else lines[0]).replace('\n', ' / ')))
    if '--out' in sys.argv:
        open(sys.argv[sys.argv.index('--out') + 1], 'wb').write(b)
    print('station blob: %d bytes, %d talks' % (len(b), len(TALK)))
