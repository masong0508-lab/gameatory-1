import sys,zlib,struct
d=open(sys.argv[1] if len(sys.argv)>1 else '/root/.pcsxr/memcards/card1.mcd','rb').read()
assert d[:2]==b'MC' and len(d)==131072
x=0
for i in range(127): x^=d[i]
print('frame0 checksum ok',x==d[127])
for k in range(1,16):
    e=d[k*128:k*128+128]; c=0
    for i in range(127): c^=e[i]
    if e[0]!=0xa0: print('dir',k,'state %02x size %d next %04x name %r chk %s'%(e[0],struct.unpack('<I',e[4:8])[0],struct.unpack('<H',e[8:10])[0],e[10:30].rstrip(b'\0'),c==e[127]))
# find file
for k in range(1,16):
    e=d[k*128:k*128+128]
    if e[0]==0x51 and e[10:28]==b'BESLES-99901SFBACK':
        nx=struct.unpack('<H',e[8:10])[0]+1; img=d[k*8192:k*8192+8192]+d[nx*8192:nx*8192+8192]
        print('blocks',k,nx,'hdr',img[:4],'icon flag %02x blocks %d'%(img[2],img[3]),'title',img[4:40].decode('shift_jis','replace'))
        m=struct.unpack('<5I',img[3*128:3*128+20]); pay=img[0x200:0x200+8192]
        print('meta magic %08x ver %d seq %d n %d crc %08x  payload crc %08x'%(m[0],m[1],m[2],m[3],m[4],zlib.crc32(pay)&0xffffffff),'boot',struct.unpack('<I',pay[:4])[0],'ee[100]=%02x ee[8191]=%02x'%(pay[100],pay[8191]))
