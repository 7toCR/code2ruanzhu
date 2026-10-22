#include "board.h"
#include "app/control.h"
#include "app/uart_proto.h"
#include "drv/sensor.h"
#include "drv/heater.h"

#define MAIN_TICK_MS        10u
#define DEFAULT_SETPOINT    400     /* 0.1 ℃，即 40.0 ℃ */

int main(void)
{
    uint32_t last = 0;

    board_init();
    sensor_init();
    heater_init();
    ctrl_init(DEFAULT_SETPOINT);
    proto_init();

    for (;;) {
        uint32_t now = board_tick_ms();
        if ((uint32_t)(now - last) < MAIN_TICK_MS) {
            continue;
        }
        last = now;
        ctrl_update_input(sensor_read(), sensor_fault());
        ctrl_task();
        uart_task();
    }
}
