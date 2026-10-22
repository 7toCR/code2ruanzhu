#ifndef CONTROL_H
#define CONTROL_H

#include <stdint.h>

void    ctrl_init(int16_t setpoint);
void    ctrl_update_input(int16_t temp, int fault);
void    ctrl_task(void);
int     ctrl_set_target(int16_t setpoint);
int16_t ctrl_temp(void);
int     ctrl_fault(void);

#endif
