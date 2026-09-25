#!/usr/bin/env python3
"""Build the Burai Fighter Deluxe menu patch for CRC32 3C86F5DB.

Assembly is emitted with a tiny label/fixup helper so the hack can be audited
and rebuilt without a particular assembler installation.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    raise SystemExit("Usage: python3 source/build_burai.py /path/to/original.gb")
SOURCE = Path(sys.argv[1])
BUILD = ROOT.parent / "build"
BUILD.mkdir(exist_ok=True)
OUT = BUILD / "Burai Fighter Deluxe - Level Select v1.0.gb"
IPS = BUILD / "Burai Fighter Deluxe - Level Select.ips"

class Code:
    def __init__(self, base: int):
        self.base = base
        self.data = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    def here(self) -> int: return self.base + len(self.data)
    def label(self, name: str):
        assert name not in self.labels, name
        self.labels[name] = self.here()
    def b(self,*values: int): self.data.extend(values)
    def word(self,value: int): self.b(value&255,value>>8&255)
    def addr(self,op: int,value: int): self.b(op);self.word(value)
    def link(self,op: int,name: str,kind: str="word"):
        self.b(op)
        self.fixups.append((len(self.data),name,kind))
        self.b(0,0) if kind=="word" else self.b(0)
    def jp(self,name: str): self.link(0xC3,name)
    def call(self,name: str): self.link(0xCD,name)
    def jr(self,op: int,name: str): self.link(op,name,"rel")
    def text(self,s: str): self.data.extend(s.encode("ascii")+b"\0")
    def finish(self) -> bytes:
        for pos,name,kind in self.fixups:
            target=self.labels[name]
            if kind=="word": struct.pack_into("<H",self.data,pos,target)
            else:
                delta=target-(self.base+pos+1)
                if not -128<=delta<=127: raise ValueError(f"{name}: JR {delta} out of range")
                self.data[pos]=delta&255
        return bytes(self.data)

def ld_a(c: Code,value: int): c.b(0x3E,value)
def read(c: Code,addr: int): c.addr(0xFA,addr)
def write(c: Code,addr: int): c.addr(0xEA,addr)
def hl(c: Code,addr: int): c.addr(0x21,addr)
def de(c: Code,addr: int): c.addr(0x11,addr)
def call(c: Code,addr: int): c.addr(0xCD,addr)
def bit(c: Code,n: int): c.b(0xCB,0x47+n*8)
def draw(c: Code,s: str,dest: int):
    c.link(0x21,"text_"+s)
    de(c,dest)
    c.call("draw")

def build():
    raw=bytearray(SOURCE.read_bytes())
    assert len(raw)==65536 and zlib.crc32(raw)==0x3C86F5DB, "Wrong ROM revision"
    assert raw[0x147]==1 and raw[0x148]==1 and raw[0x149]==0
    rom=raw.copy()
    # VBlank expects bank 1 for graphics, bank 3 for its music update, then
    # bank 1 again for sound. Restore the options menu bank only after that.
    # Preserve $0060 (joypad interrupt RETI) and use padding beside it.
    assert rom[0x51:0x58]==b"\0"*7
    assert rom[0x61:0x6a]==b"\0"*9
    rom[0x51:0x58]=bytes.fromhex("cd 33 18 cd 61 00 c9")
    rom[0x61:0x6a]=bytes.fromhex("fa f6 d1 b7 c8 ea 80 21 c9")
    assert rom[0x8d:0x90]==bytes.fromhex("cd a4 48")
    assert rom[0xa0:0xa3]==bytes.fromhex("cd 33 18")
    rom[0x8d:0x90]=bytes.fromhex("cd e8 00")
    rom[0xa0:0xa3]=bytes.fromhex("cd 51 00")
    # A bank-0 return trampoline and bank-3 entry, used only by Level Select.
    assert rom[0x08:0x10]==b"\0"*8
    assert rom[0xe8:0x100]==b"\0"*24
    rom[0x08:0x0e]=bytes.fromhex("3e 01 ea 80 21 e9")
    rom[0xe8:0xf0]=bytes.fromhex("3e 01 ea 80 21 c3 a4 48")
    rom[0xf7:0x100]=bytes.fromhex("f3 3e 03 ea 80 21 c3 f0 5d")
    # A fixed-bank exit switches to bank 1 before the original title loader.
    # Its caller preloads HL with the ROM bank register address $2180.
    assert rom[0xf0:0xf6]==bytes(6)
    rom[0xf0:0xf6]=bytes.fromhex("3e 01 77 c3 bd 02")
    # Original NEW GAME reaches the original difficulty page and start path.
    # The fourth title item dispatches separately; its settings feed the
    # existing difficulty screen, whose confirmation optionally applies them.
    assert rom[0x37d:0x382]==bytes.fromhex("21 40 ff cb c6")
    rom[0x37d:0x382]=bytes.fromhex("cd 2c 75 00 00")
    assert rom[0x3f8:0x400]==bytes.fromhex("3e 9b cd 18 18 c3 4c 04")
    rom[0x3f8:0x400]=bytes.fromhex("c3 ac 71 00 00 00 00 00")
    for pos,old,new in ((0x374,0x54,0x4c),
                        (0x376,0x2e,0x1e), # title cursor x: center the block
                        (0x3b7,0x54,0x4c), # downward wrap reaches new NEW GAME row
                        (0x3c3,0x4c,0x44), # upward wrap: one row above NEW GAME
                        (0x422,0x03,0x04),(0x445,0x02,0x03),
                        (0x385,0xff,0x01)):
        assert rom[pos]==old;rom[pos]=new
    assert rom[0x4e3:0x4e6]==bytes.fromhex("c3 03 09")
    rom[0x4e3:0x4e6]=bytes.fromhex("c3 c9 73")
    assert rom[0x147b:0x1480]==bytes.fromhex("3e 1c cd 87 1c")
    rom[0x147b:0x1480]=bytes.fromhex("c3 a1 73 00 00")
    # The vanilla post-Ace route still preselects Ultimate. A Level Select
    # run preserves the player's selected difficulty when its fourth row draws.
    assert rom[0x522:0x527]==bytes.fromhex("3e 03 ea d8 c0")
    rom[0x522:0x527]=bytes.fromhex("cd d0 71 00 00")
    # Both the three-row and the Ultimate-enabled difficulty loops read
    # c0e4. Intercept their input read; for all non-B keys return the exact
    # original value. B returns to the screen this difficulty came from.
    for pos in (0x4B6,0x545):
        assert rom[pos:pos+3]==bytes.fromhex("fa e4 c0")
        rom[pos:pos+3]=bytes.fromhex("cd 30 72")
    # Shift the three menu lines up one row, add the fourth line, and leave
    # the logo and every footer tile at their original positions.
    t=Code(0x752C)
    hl(t,0xFF40);t.b(0xCB,0xBE) # LCD off
    hl(t,0x9A00);de(t,0x99DE);t.b(0x01,0x60,0x00)
    t.label("move");t.b(0x2A,0x12,0x13,0x0B,0x78,0xB1);t.jr(0x20,"move")
    hl(t,0x9A40);t.b(0x06,0x20,0xAF)
    t.label("erase");t.b(0x22,0x05);t.jr(0x20,"erase")
    hl(t,0x9A4A)
    for ch in "LEVEL SELECT":t.b(0x36,ord(ch)-32,0x23)
    hl(t,0xFF40);t.b(0xCB,0xFE,0xCB,0xC6,0xC9) # LCD on, original SET 0
    title=t.finish();print("title",len(title));assert len(title)<=112
    assert rom[0x752c:0x752c+112]==bytes(112)
    rom[0x752c:0x752c+len(title)]=title
    # In the password editor B normally erases the last character. If its
    # index is already zero, return to the title without changing passwords.
    p=Code(0x73A1)
    read(p,0xD105);p.b(0xB7);p.jr(0x28,"leave")
    ld_a(p,0x1C);call(p,0x1C87);p.addr(0xC3,0x1480)
    p.label("leave");p.b(0xAF);hl(p,0xC0D4)
    p.b(0x22,0x22,0x77) # clear d4, d5, d6 together
    p.addr(0xC3,0x02BD)
    password=p.finish();assert len(password)<=0x73B9-0x73A1
    assert rom[0x73A1:0x73A1+len(password)]==bytes(len(password))
    rom[0x73A1:0x73A1+len(password)]=password
    # The difficulty page reloads the title logo's $8800-$8fff graphic
    # tiles. Restore the logo from its original bank-2 source, while the LCD
    # is off, before handing control to the preserved settings tilemap.
    g=Code(0x757B)
    g.b(0xF3)
    g.label("wait");g.b(0xF0,0x44,0xFE,0x91);g.jr(0x38,"wait")
    hl(g,0xFF40);g.b(0xCB,0xBE)
    ld_a(g,2);hl(g,0x4800);de(g,0x8800);g.b(0x01,0x00,0x08)
    call(g,0x01B5);g.addr(0xC3,0x00F7)
    graphic=g.finish();assert len(graphic)<=0x759C-0x757B
    assert rom[0x757B:0x757B+len(graphic)]==bytes(len(graphic))
    rom[0x757B:0x757B+len(graphic)]=graphic

    d=Code(0x71AC)
    read(d,0xD103);d.b(0xFE,3);d.jr(0x20,"ordinary")
    ld_a(d,0x9B);call(d,0x1818)
    call(d,0x0FBF)
    d.addr(0xC3,0x00F7)
    d.label("ordinary");ld_a(d,0x9B);call(d,0x1818);d.addr(0xC3,0x044C)
    dispatch=d.finish();print("dispatch",len(dispatch));assert len(dispatch)<=95
    assert rom[0x71ac:0x71ac+95]==bytes(95)
    rom[0x71ac:0x71ac+len(dispatch)]=dispatch
    assert len(dispatch)<=0x71C6-0x71AC
    assert rom[0x71c6:0x71ca]==bytes(4)
    rom[0x71c6:0x71ca]=bytes.fromhex("fb c3 95 03") # EI after bank switch
    u=Code(0x71D0)
    read(u,0xD1F7);u.b(0xB7,0xC0)
    ld_a(u,3);write(u,0xC0D8);u.b(0xC9)
    unlock=u.finish();assert rom[0x71d0:0x71d0+len(unlock)]==bytes(len(unlock))
    rom[0x71d0:0x71d0+len(unlock)]=unlock
    w=Code(0x71DC)
    read(w,0xD1F2)
    w.b(0xFE,4);w.jr(0x30,"all")
    write(w,0xD1C0) # 1 Laser, 2 Ring, 3 Missile
    w.b(0x3D,0x5F,0x16,0);hl(w,0xD1BD);w.b(0x19,0x36,10)
    w.label("done");w.addr(0xC3,0x0903)
    w.label("all");w.b(0xD6,3);write(w,0xD1C0)
    ld_a(w,10)
    for addr in (0xD1BD,0xD1BE,0xD1BF):write(w,addr)
    w.addr(0xC3,0x0903)
    equipment=w.finish();print("equipment",len(equipment));assert len(equipment)<=0x720B-0x71DC
    assert rom[0x71dc:0x71dc+len(equipment)]==bytes(len(equipment))
    rom[0x71dc:0x71dc+len(equipment)]=equipment
    # The game's BCD 99 is the no-lives-remaining result of subtracting from
    # zero. Reserve 99 as an infinite-lives sentinel by intercepting the loss
    # only for that value; other counts take the exact original BCD route.
    assert rom[0x0ab6:0x0ab9]==bytes.fromhex("fa c9 c0")
    rom[0x0ab6:0x0ab9]=bytes.fromhex("c3 17 72")
    death=Code(0x7217)
    read(death,0xC0C9);death.b(0xFE,0x99);death.jr(0x28,"restart")
    death.b(0xD6,1,0x27,0xFE,0x99);death.jr(0x28,"game_over")
    write(death,0xC0C9)
    death.label("restart");death.addr(0xC3,0x0920)
    death.label("game_over");death.addr(0xC3,0x0AC6)
    lost=death.finish();assert len(lost)<=0x724B-0x7217
    assert rom[0x7217:0x7217+len(lost)]==bytes(len(lost))
    rom[0x7217:0x7217+len(lost)]=lost
    difback=Code(0x7230)
    read(difback,0xC0E4);bit(difback,1);difback.b(0xC8) # RET Z
    difback.b(0xE1) # discard the CALL return address before either JP
    read(difback,0xD1F7);difback.b(0xB7)
    difback.addr(0xCA,0x02BD) # NEW GAME -> original title loader
    difback.addr(0xC3,0x757B) # LEVEL SELECT -> restore logo, then resume
    inp=difback.finish();assert len(inp)<=0x724B-0x7230
    assert rom[0x7230:0x7230+len(inp)]==bytes(len(inp))
    rom[0x7230:0x7230+len(inp)]=inp

    s=Code(0x73C9)
    read(s,0xD1F7);s.b(0xB7);s.jr(0x28,"vanilla")
    s.b(0xAF);write(s,0xD1F7)
    read(s,0xD1F8);write(s,0xC0D9)
    read(s,0xD1F0);write(s,0xC0D2)
    read(s,0xD1F1);s.b(0x5F,0x16,0)
    s.link(0x21,"life_table");s.b(0x19,0x7E);write(s,0xC0C9)
    read(s,0xD1F2);s.b(0xB7);s.jr(0x28,"vanilla")
    s.addr(0xC3,0x71DC) # equipment choices finish in a separate bank-1 stub
    s.label("vanilla");s.addr(0xC3,0x0903)
    s.label("life_table");s.b(2,4,8,0x99)
    start=s.finish();print("start hook",len(start));assert len(start)<=66
    assert rom[0x73c9:0x73c9+66]==bytes(66)
    rom[0x73c9:0x73c9+len(start)]=start
    c=Code(0x5DF0)
    # Dedicated config state: stage, lives choice (3/5/9/infinite), weapon,
    # cursor, previous/new joypad, ISR bank flag, pending launch, old unlock.
    c.b(0xAF)
    for addr in (0xD1F0,0xD1F2,0xD1F3,0xD1F4,0xD1F5,0xD1F7):write(c,addr)
    ld_a(c,1);write(c,0xD1F1)
    ld_a(c,3);write(c,0xD1F6)
    # Preserve the title logo in rows 8-13. Snapshot rows 14-25 and put
    # the original TAXAN logo and copyright lines back into rows 20-24.
    c.label("wait_lcd");c.b(0xF0,0x44,0xFE,0x91);c.jr(0x38,"wait_lcd")
    hl(c,0xFF40);c.b(0xCB,0xBE) # RES 7,[HL]
    hl(c,0x99C0);de(c,0x9C00);c.b(0x01,0x80,0x01)
    c.label("backup");c.b(0x2A,0x12,0x13,0x0B,0x78,0xB1);c.jr(0x20,"backup")
    hl(c,0x99C0);c.b(0x01,0x80,0x01) # BC = 12 * 32
    c.label("clear");c.b(0x36,0,0x23,0x0B,0x78,0xB1);c.jr(0x20,"clear")
    hl(c,0x9CC0);de(c,0x9A80);c.b(0x01,0xA0,0x00)
    c.label("footer");c.b(0x2A,0x12,0x13,0x0B,0x78,0xB1);c.jr(0x20,"footer")
    # Hide the old difficulty cursor sprite. VBlank DMA copies this shadow OAM.
    hl(c,0xC000);c.b(0x06,0xA0,0xAF)
    c.label("clear_oam");c.b(0x22,0x05);c.jr(0x20,"clear_oam")
    for s,at in (("LEVEL SELECT",0x99E9),
                 ("STAGE",0x9A09),("LIVES",0x9A29),
                 ("WEAPONS",0x9A49)):
        draw(c,s,at)
    c.call("update")
    hl(c,0xFF40);c.b(0xCB,0xFE,0xFB) # SET 7,[HL], EI
    # The key that selected a difficulty may still be held. Take one sample
    # before accepting new button edges in this screen.
    c.call("poll")

    c.label("loop")
    call(c,0x1216) # Wait for original VBlank signal.
    c.call("poll")
    read(c,0xD1F5)
    bit(c,3);c.jr(0x28,"not_start");c.jp("start")
    c.label("not_start")
    bit(c,1);c.jr(0x28,"not_back");c.jp("back")
    c.label("not_back")
    bit(c,6);c.jr(0x20,"up")
    bit(c,7);c.jr(0x20,"down")
    bit(c,4);c.jr(0x20,"plus")
    bit(c,0);c.jr(0x20,"plus")
    bit(c,5);c.jr(0x20,"minus")
    c.jp("loop")

    c.label("up")
    read(c,0xD1F3);c.b(0x3D,0xFE,0xFF);c.jr(0x20,"sel_store")
    ld_a(c,2)
    c.label("sel_store");write(c,0xD1F3);c.jp("refresh")
    c.label("down")
    read(c,0xD1F3);c.b(0x3C,0xFE,0x03);c.jr(0x20,"sel_store")
    c.b(0xAF);c.jr(0x18,"sel_store")
    c.label("plus")
    read(c,0xD1F3);c.b(0xB7);c.jr(0x20,"toggle")
    read(c,0xD1F0);c.b(0x3C,0xFE,0x05);c.jr(0x20,"stage_store")
    c.b(0xAF);c.jr(0x18,"stage_store")
    c.label("minus")
    read(c,0xD1F3);c.b(0xB7);c.jr(0x20,"toggle_minus")
    read(c,0xD1F0);c.b(0x3D,0xFE,0xFF);c.jr(0x20,"stage_store")
    ld_a(c,4)
    c.label("stage_store");write(c,0xD1F0);c.jp("refresh")
    c.label("toggle")
    read(c,0xD1F3);c.b(0xFE,1);c.jr(0x20,"gear_toggle")
    read(c,0xD1F1);c.b(0x3C,0xFE,4);c.jr(0x20,"life_store")
    c.b(0xAF)
    c.label("life_store");write(c,0xD1F1);c.jr(0x18,"refresh")
    c.label("gear_toggle")
    read(c,0xD1F2);c.b(0x3C,0xFE,7);c.jr(0x20,"gear_store")
    c.b(0xAF)
    c.label("gear_store");write(c,0xD1F2)
    c.label("refresh");c.call("safe_update");c.jp("loop")
    c.label("toggle_minus")
    read(c,0xD1F3);c.b(0xFE,1);c.jr(0x20,"gear_minus")
    read(c,0xD1F1);c.b(0x3D,0xFE,0xFF);c.jr(0x20,"life_store")
    ld_a(c,3);c.jr(0x18,"life_store")
    c.label("gear_minus")
    read(c,0xD1F2);c.b(0x3D,0xFE,0xFF);c.jr(0x20,"gear_store")
    ld_a(c,6);c.jr(0x18,"gear_store")

    c.label("back")
    c.addr(0xC3,0x7E80)
    c.label("start")
    read(c,0xC0D9);write(c,0xD1F8)
    ld_a(c,1);write(c,0xC0D9);write(c,0xD1F7)
    c.b(0xAF);write(c,0xC0D8)
    c.b(0xF3,0xAF);write(c,0xD1F6);hl(c,0x0463);c.addr(0xC3,0x0008)

    # Newly pressed button edges. Layout matches the game's input bits:
    # A/B/Select/Start = bits 0..3; Right/Left/Up/Down = bits 4..7.
    c.label("poll")
    ld_a(c,0x20);c.b(0xE0,0,0xF0,0,0xF0,0,0x2F,0xCB,0x37,0xE6,0xF0,0x47)
    ld_a(c,0x10);c.b(0xE0,0,0xF0,0,0xF0,0,0x2F,0xE6,0x0F,0xB0,0x47)
    ld_a(c,0x30);c.b(0xE0,0)
    read(c,0xD1F4);c.b(0x2F,0xA0);write(c,0xD1F5)
    c.b(0x78);write(c,0xD1F4);c.b(0xC9)

    c.label("update")
    read(c,0xD1F0);c.b(0xC6,0x65);write(c,0x9A11)
    # The field text is always rewritten from its beginning and padded with
    # spaces so toggling a short value never leaves stray characters.
    read(c,0xD1F1);c.b(0x87,0x5F,0x16,0)
    c.link(0x21,"lives_table");c.b(0x19,0x2A,0x66,0x6F)
    de(c,0x9A31);c.call("draw")
    read(c,0xD1F2);c.b(0x87,0x5F,0x16,0)
    c.link(0x21,"weapon_table");c.b(0x19,0x2A,0x66,0x6F)
    de(c,0x9A51);c.call("draw")
    read(c,0xD1F2);c.b(0x87,0x5F,0x16,0)
    c.link(0x21,"weapon_subtable");c.b(0x19,0x2A,0x66,0x6F)
    de(c,0x9A71);c.call("draw")
    c.b(0xAF)
    for addr in (0x9A07,0x9A27,0x9A47):write(c,addr)
    read(c,0xD1F3);c.b(0xB7);c.jr(0x28,"mark_stage")
    c.b(0x3D);c.jr(0x28,"mark_lives")
    ld_a(c,0x1D);write(c,0x9A47);c.b(0xC9)
    c.label("mark_stage");ld_a(c,0x1D);write(c,0x9A07);c.b(0xC9)
    c.label("mark_lives");ld_a(c,0x1D);write(c,0x9A27);c.b(0xC9)

    # Update in VBlank without switching the LCD off (which flashed white).
    c.label("safe_update")
    c.b(0xF3)
    c.label("safe_ready");c.b(0xF0,0x44,0xFE,0x90);c.jr(0x30,"safe_ready")
    c.label("safe_wait");c.b(0xF0,0x44,0xFE,0x90);c.jr(0x38,"safe_wait")
    c.call("update")
    c.b(0xFB,0xC9)

    # Keep the small drawing helper and three pointer tables in the unused
    # bank-3 tail to leave room for directional controls in the menu body.
    x=Code(0x7F10)
    x.label("draw")
    x.b(0x2A,0xB7,0xC8) # [HL++], terminator, RET if zero
    # The font's number tiles live at $64+digit, while uppercase letters
    # follow ASCII minus $20. Handle both in one field renderer.
    x.b(0xFE,0x30);x.jr(0x38,"letter")
    x.b(0xFE,0x3A);x.jr(0x30,"letter")
    x.b(0xC6,0x34);x.jr(0x18,"store")
    x.label("letter");x.b(0xD6,0x20)
    x.label("store");x.b(0x12,0x13)
    x.jr(0x18,"draw")
    x.label("weapon_table")
    for s in ("BASE   ","LASER  ","RING   ","MISSILE",
              "FULL   ","FULL   ","FULL   "):
        x.fixups.append((len(x.data),"text_"+s,"word"));x.b(0,0)
    x.label("weapon_subtable")
    for s in ("       ",)*4+("LASER  ","RING   ","MISSILE"):
        x.fixups.append((len(x.data),"text_"+s,"word"));x.b(0,0)
    x.label("lives_table")
    for s in ("3       ","5       ","9       ","INFINITE"):
        x.fixups.append((len(x.data),"text_"+s,"word"));x.b(0,0)
    # $00F7 enters here on either the first Level Select visit or when B is
    # pressed on its difficulty page. On return, the BG at $9800 still holds
    # the settings screen; only the difficulty window covers it. Preserve all
    # selected values, hide that window/cursor, and consume the held B press.
    x.label("entry")
    read(x,0xD1F7);x.b(0xB7);x.addr(0xCA,0x5DF0)
    x.label("resume")
    ld_a(x,0x90);x.b(0xE0,0x4A) # WY=$90 hides the difficulty window
    ld_a(x,3);write(x,0xD1F6)
    hl(x,0xC000);x.b(0x06,0xA0,0xAF)
    x.label("clear_cursor");x.b(0x22,0x05);x.jr(0x20,"clear_cursor")
    hl(x,0xFF40);x.b(0xCB,0xFE) # turn LCD back on after restoring logo
    x.call("safe_update")
    x.call("poll")
    x.b(0xFB);x.jp("loop")
    strings=bytearray()
    for s in ("LEVEL SELECT","STAGE","LIVES","WEAPONS",
              "BASE   ","LASER  ","RING   ","MISSILE",
              "FULL   ","       ","3       ","5       ","9       ","INFINITE"):
        c.labels["text_"+s]=x.labels["text_"+s]=0x7DD6+len(strings)
        strings.extend(s.encode("ascii")+b"\0")
    c.labels.update(x.labels)
    x.labels.update(c.labels)
    body=c.finish()
    extra=x.finish()
    assert rom[0xfd:0x100]==bytes.fromhex("c3 f0 5d")
    rom[0xfe:0x100]=struct.pack("<H",x.labels["entry"])
    print(f"bank 3 menu: {len(body)} bytes of 529 free, strings: {len(strings)} of 299")
    if len(body)>529:raise ValueError("menu overflows bank 3 free area")
    if len(strings)>299:raise ValueError("strings overflow bank 3 free area")
    start=0xDDF0
    assert rom[start:start+529]==b"\0"*529
    rom[start:start+len(body)]=body
    assert rom[0xFDD6:0xFDD6+299]==b"\0"*299
    rom[0xFDD6:0xFDD6+len(strings)]=strings
    assert rom[0xFF10:0xFF10+len(extra)]==bytes(len(extra))
    rom[0xFF10:0xFF10+len(extra)]=extra
    # Restore the original title tilemap snapshot and cursor on B. The
    # settings page inherited its logo, so no slow title reload is needed.
    b=Code(0x7E80)
    read(b,0xD1F7);b.b(0xB7);b.jr(0x28,"quick")
    # Difficulty overwrites our backup tilemap at $9C00. Reload the title,
    # restoring its original Ultimate availability and clearing the origin.
    b.b(0xF3,0xAF);write(b,0xD1F7);write(b,0xD1F6)
    read(b,0xD1F8);write(b,0xC0D9)
    hl(b,0x2180);b.addr(0xC3,0x00F0)
    b.label("quick")
    b.b(0xF3)
    b.label("wait");b.b(0xF0,0x44,0xFE,0x91);b.jr(0x38,"wait")
    hl(b,0xFF40);b.b(0xCB,0xBE)
    hl(b,0x9C00);de(b,0x99C0);b.b(0x01,0x80,0x01)
    b.label("restore");b.b(0x2A,0x12,0x13,0x0B,0x78,0xB1);b.jr(0x20,"restore")
    for addr,value in ((0xC000,0x4C),(0xC001,0x1E),(0xC002,0x1D),
                       (0xC003,0),(0xD103,0),(0xD1F6,0)):
        ld_a(b,value);write(b,addr)
    hl(b,0xFF40);b.b(0xCB,0xC6,0xCB,0xCE,0xCB,0xFE)
    call(b,0xFF80) # copy the restored cursor sprite to hardware OAM
    hl(b,0x71C6);b.addr(0xC3,0x0008)
    back=b.finish();assert len(back)<0x80
    assert rom[0xFE80:0xFE80+len(back)]==bytes(len(back))
    rom[0xFE80:0xFE80+len(back)]=back

    # Nintendo cartridge checksums. The image remains 64 KB MBC1/no RAM.
    rom[0x14d]=(-sum(rom[0x134:0x14d])-25)&255
    total=(sum(rom[:0x14e])+sum(rom[0x150:]))&65535
    rom[0x14e:0x150]=struct.pack(">H",total)
    OUT.write_bytes(rom)
    # IPS hunks, contiguous diff runs, capped at 65535 bytes each.
    ips=bytearray(b"PATCH")
    changed=[i for i,(a,b) in enumerate(zip(raw,rom)) if a!=b]
    runs=[]
    for p in changed:
        if runs and p==runs[-1][-1]+1 and len(runs[-1])<65535:runs[-1].append(p)
        else:runs.append([p])
    for run in runs:
        pos=run[0];data=rom[pos:run[-1]+1]
        ips.extend(pos.to_bytes(3,"big")+len(data).to_bytes(2,"big")+data)
    ips.extend(b"EOF")
    IPS.write_bytes(ips)
    print("ROM",OUT,"SHA256",hashlib.sha256(rom).hexdigest(),"IPS",len(ips),"bytes")

if __name__=="__main__":build()
