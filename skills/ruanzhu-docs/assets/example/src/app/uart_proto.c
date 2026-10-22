#include "uart_proto.h"
#include "control.h"
#include "../board.h"

#define FRAME_MAX   8u

/* 帧格式：A5 | 命令字 | 长度 N | 数据 N 字节 | 校验和（命令字至数据的累加和低 8 位） */
enum { ST_HEAD, ST_CMD, ST_LEN, ST_DATA, ST_SUM };

static uint8_t s_st;
static uint8_t s_cmd;
static uint8_t s_len;
static uint8_t s_pos;
static uint8_t s_sum;
static uint8_t s_buf[FRAME_MAX];

static void reply(uint8_t cmd, const uint8_t *data, uint8_t len)
{
    uint8_t out[FRAME_MAX + 4];
    uint8_t i, sum = (uint8_t)(cmd + len);

    out[0] = PROTO_HEAD;
    out[1] = cmd;
    out[2] = len;
    for (i = 0; i < len; i++) {
        out[3 + i] = data[i];
        sum = (uint8_t)(sum + data[i]);
    }
    out[3 + len] = sum;
    board_uart_write(out, (uint16_t)(len + 4u));
}

static void proto_handle(void)
{
    uint8_t ack[3];
    int16_t t;

    switch (s_cmd) {
    case PROTO_CMD_READ:
        t = ctrl_temp();
        ack[0] = (uint8_t)(t & 0xFF);
        ack[1] = (uint8_t)((t >> 8) & 0xFF);
        ack[2] = (uint8_t)ctrl_fault();
        reply(PROTO_CMD_READ, ack, 3);
        break;
    case PROTO_CMD_SET:
        t = (int16_t)(s_buf[0] | (s_buf[1] << 8));
        ack[0] = (s_len == 2u && ctrl_set_target(t) == 0) ? PROTO_ACK_OK : PROTO_ACK_ERR;
        reply(PROTO_CMD_SET, ack, 1);
        break;
    default:
        ack[0] = PROTO_ACK_ERR;
        reply(s_cmd, ack, 1);
        break;
    }
}

void proto_init(void)
{
    s_st = ST_HEAD;
}

void uart_task(void)
{
    uint8_t ch;

    while (board_uart_getc(&ch)) {
        switch (s_st) {
        case ST_HEAD:
            if (ch == PROTO_HEAD) {
                s_st = ST_CMD;
            }
            break;
        case ST_CMD:
            s_cmd = ch;
            s_sum = ch;
            s_st = ST_LEN;
            break;
        case ST_LEN:
            s_len = ch;
            s_sum = (uint8_t)(s_sum + ch);
            s_pos = 0;
            s_st = (ch == 0u) ? ST_SUM : ((ch <= FRAME_MAX) ? ST_DATA : ST_HEAD);
            break;
        case ST_DATA:
            s_buf[s_pos++] = ch;
            s_sum = (uint8_t)(s_sum + ch);
            if (s_pos >= s_len) {
                s_st = ST_SUM;
            }
            break;
        default:
            if (ch == s_sum) {
                proto_handle();
            }
            s_st = ST_HEAD;
            break;
        }
    }
}
