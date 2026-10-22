#include "control.h"
#include "../drv/heater.h"

#define TEMP_LIMIT      850     /* 上限 85.0 ℃ */
#define SET_MIN         200     /* 设定范围 20.0 ℃ */
#define SET_MAX         800     /* 设定范围 80.0 ℃ */
#define KP_X10          35      /* 比例系数 3.5 */
#define KI_X100         8       /* 积分系数 0.08 */
#define INT_LIMIT       12000

static int16_t s_set;
static int16_t s_temp;
static int     s_fault;
static int32_t s_int;

void ctrl_init(int16_t setpoint)
{
    s_set = setpoint;
    s_temp = 0;
    s_fault = 0;
    s_int = 0;
}

void ctrl_update_input(int16_t temp, int fault)
{
    s_temp = temp;
    s_fault = fault;
}

void ctrl_task(void)
{
    int32_t e, out;

    if (s_fault || s_temp >= TEMP_LIMIT) {
        s_int = 0;
        heater_off();
        return;
    }
    e = (int32_t)s_set - (int32_t)s_temp;
    s_int += e;
    if (s_int > INT_LIMIT) {
        s_int = INT_LIMIT;
    } else if (s_int < -INT_LIMIT) {
        s_int = -INT_LIMIT;
    }
    out = (e * KP_X10) / 10 + (s_int * KI_X100) / 100;
    if (out < 0) {
        out = 0;
    } else if (out > 100) {
        out = 100;
    }
    heater_set((uint8_t)out);
}

int ctrl_set_target(int16_t setpoint)
{
    if (setpoint < SET_MIN || setpoint > SET_MAX) {
        return -1;
    }
    s_set = setpoint;
    return 0;
}

int16_t ctrl_temp(void)
{
    return s_temp;
}

int ctrl_fault(void)
{
    return s_fault;
}
