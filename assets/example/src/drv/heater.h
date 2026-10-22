#ifndef HEATER_H
#define HEATER_H

#include <stdint.h>

void heater_init(void);
void heater_set(uint8_t duty_percent);
void heater_off(void);

#endif
