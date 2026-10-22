#include "sensor.h"
#include "../board.h"

#define ADC_TIMEOUT_MS      2u
#define FAIL_LIMIT          3u
#define AVG_N               8u

/* NTC 分段线性表：ADC 采样值（12 位）与温度（0.1 ℃）对应 */
static const uint16_t adc_tab[]  = { 3900, 3500, 2900, 2200, 1500, 950, 560, 330 };
static const int16_t  temp_tab[] = {  -100,    0,  150,  300,  450,  600,  750,  900 };

static int16_t  s_hist[AVG_N];
static uint8_t  s_idx;
static uint8_t  s_fill;
static uint8_t  s_fail;
static int      s_fault;
static int16_t  s_last;

static int16_t adc_to_temp(uint16_t v)
{
    uint8_t i;
    if (v >= adc_tab[0]) {
        return temp_tab[0];
    }
    for (i = 1; i < sizeof(adc_tab) / sizeof(adc_tab[0]); i++) {
        if (v >= adc_tab[i]) {
            int32_t dv = (int32_t)adc_tab[i - 1] - (int32_t)v;
            int32_t span = (int32_t)adc_tab[i - 1] - (int32_t)adc_tab[i];
            int32_t dt = (int32_t)temp_tab[i] - (int32_t)temp_tab[i - 1];
            return (int16_t)(temp_tab[i - 1] + dv * dt / span);
        }
    }
    return temp_tab[sizeof(temp_tab) / sizeof(temp_tab[0]) - 1];
}

void sensor_init(void)
{
    s_idx = 0;
    s_fill = 0;
    s_fail = 0;
    s_fault = 0;
    s_last = 0;
}

int16_t sensor_read(void)
{
    uint32_t t0 = board_tick_ms();
    int32_t sum = 0;
    uint8_t i;

    board_adc_start();
    while (!board_adc_done()) {
        if ((uint32_t)(board_tick_ms() - t0) >= ADC_TIMEOUT_MS) {
            if (++s_fail >= FAIL_LIMIT) {
                s_fault = 1;
            }
            return s_last;
        }
    }
    s_hist[s_idx] = adc_to_temp(board_adc_value());
    s_idx = (uint8_t)((s_idx + 1u) % AVG_N);
    if (s_fill < AVG_N) {
        s_fill++;
    }
    for (i = 0; i < s_fill; i++) {
        sum += s_hist[i];
    }
    s_last = (int16_t)(sum / s_fill);
    s_fail = 0;
    s_fault = 0;
    return s_last;
}

int sensor_fault(void)
{
    return s_fault;
}
