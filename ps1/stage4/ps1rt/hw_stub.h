/* -DCDSIM (ps1sim unicorn lockstep, no SIO/SPU model): no-op versions of the pad / card / CD-DA API */
#ifndef HW_STUB_H
#define HW_STUB_H
u16 pad_raw, pad_prev; u32 pad_extra, cdda_last, cdda_playing, sv_ok_writes;
static u32 pad_poll(void){ return 0x3ff; }
static int sv_load(u8*e,u32 n){ return -1; } static void sv_dirty(u32 o,u32 l){} static void sv_service(void){}
static void cdda_init(void){} static void cdda_play(u32 t){} static void cdda_stop(void){} static void cdda_service(void){} static void cdda_hold(void){} static void cdda_release(void){}
#endif
