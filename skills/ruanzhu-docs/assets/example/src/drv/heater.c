#include "heater.h"
#include "../board.h"

void heater_init(void)
{
    heater_off();
}

void heater_set(uint8_t duty_percent)
{
    if (duty_percent > 100u) {
        duty_percent = 100u;
    }
    board_pwm_set(duty_percent);
}

void heater_off(void)
{
    board_pwm_set(0u);
}
