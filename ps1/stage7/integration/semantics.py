"""Reference ARM ALU semantics in Python (used for constant folding and unit checks)."""
M32=0xffffffff
def sra32(v,n): 
    v&=M32
    if v&0x80000000: v-=1<<32
    return (v>>n)&M32
def shift32(v,kind,amt,cin):
    """kind 0 LSL 1 LSR 2 ASR 3 ROR 4 RRX; returns (result, carry_out). amt is the effective amount (0..255)."""
    v&=M32
    if kind==4: return ((cin<<31)|(v>>1))&M32, v&1
    if amt==0: return v,cin
    if kind==0:
        if amt<32: return (v<<amt)&M32,(v>>(32-amt))&1
        if amt==32: return 0,v&1
        return 0,0
    if kind==1:
        if amt<32: return v>>amt,(v>>(amt-1))&1
        if amt==32: return 0,v>>31
        return 0,0
    if kind==2:
        if amt<32: return sra32(v,amt),(v>>(amt-1))&1
        return (M32 if v>>31 else 0),v>>31
    if kind==3:
        r=amt&31
        if r==0: return v,v>>31
        return ((v>>r)|(v<<(32-r)))&M32,(v>>(r-1))&1
def alu(opc,a,b,cin):
    """returns (res,N,Z,C,V) with C,V None for logical ops (caller supplies shifter carry)"""
    a&=M32; b&=M32
    if opc in(0,8): r=a&b; lg=1
    elif opc in(1,9): r=a^b; lg=1
    elif opc==12: r=a|b; lg=1
    elif opc==13: r=b; lg=1
    elif opc==14: r=a&~b&M32; lg=1
    elif opc==15: r=~b&M32; lg=1
    else:
        lg=0
        if opc in(2,10): x,y,c=a,b^M32,1
        elif opc==3: x,y,c=b,a^M32,1
        elif opc in(4,11): x,y,c=a,b,0
        elif opc==5: x,y,c=a,b,cin
        elif opc==6: x,y,c=a,b^M32,cin
        elif opc==7: x,y,c=b,a^M32,cin
        t=x+y+c; r=t&M32
        C=1 if t>>32 else 0
        V=1 if (~(x^y)&(x^r))>>31&1 else 0
    N=r>>31; Z=1 if r==0 else 0
    if lg: return r,N,Z,None,None
    return r,N,Z,C,V
