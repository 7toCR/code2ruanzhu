#ifndef BOARD_H
#define BOARD_H

#include <stdint.h>

/* 板级接口：由各硬件平台的移植层实现 */
void     board_init(void);
uint32_t board_tick_ms(void);
void     board_adc_start(void);
int      board_adc_done(void);
uint16_t board_adc_value(void);
void     board_pwm_set(uint8_t duty_percent);
int      board_uart_getc(uint8_t *ch);
void     board_uart_write(const uint8_t *buf, uint16_t len);

#endif
