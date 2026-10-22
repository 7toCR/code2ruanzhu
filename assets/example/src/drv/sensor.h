#ifndef SENSOR_H
#define SENSOR_H

#include <stdint.h>

void    sensor_init(void);
int16_t sensor_read(void);
int     sensor_fault(void);

#endif
