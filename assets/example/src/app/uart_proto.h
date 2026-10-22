#ifndef UART_PROTO_H
#define UART_PROTO_H

#include <stdint.h>

#define PROTO_HEAD          0xA5u
#define PROTO_CMD_READ      0x01u
#define PROTO_CMD_SET       0x02u
#define PROTO_ACK_OK        0x00u
#define PROTO_ACK_ERR       0x01u

void proto_init(void);
void uart_task(void);

#endif
