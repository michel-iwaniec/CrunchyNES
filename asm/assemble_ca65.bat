ca65 main_ca65.asm -v -g -l main_ca65.lst
ld65 -o main_ca65.nes -C main_ca65.cfg -v -m main_ca65.map -vm --dbgfile main_ca65.dbg main_ca65.o
