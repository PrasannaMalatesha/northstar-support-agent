# Order changes

Cancel, modify, and tracking. Recording a cancel or a modification waits for a person.

## ORD-CANCEL

**Rule**: An order can be cancelled only when its status is placed. Packed, shipped, and delivered orders cannot be cancelled. A cancelled order is refunded in full, including outbound shipping that was charged. Cancellation waits for a person before it is recorded.

**Applies when**: The customer wants the whole order cancelled.

**Agent must not**: Cancel a packed, shipped, or delivered order, or record the cancel before a person approves it.

**Example**: Status is placed. The proposal is a full refund including shipping, waiting for a person. The draft cites ORD-CANCEL.

## ORD-MODIFY

**Rule**: Item quantities and sizes can be changed only while the status is placed. The specialist proposes the change. A person records it. If the status is packed or later, the customer must wait for delivery and then use the return rules.

**Applies when**: The customer wants a different quantity or size before the order moves on.

**Agent must not**: Change a packed order, or record the change before a person approves it.

**Example**: Status is placed and the customer wants two kettles instead of one. The specialist proposes it and waits. The draft cites ORD-MODIFY.

## ORD-TRACK

**Rule**: Tracking facts are whatever the order record stores: status, ship date, and delivery date. If a date is empty, say it is not on the order. Do not invent a carrier name, a tracking number, or a scan event.

**Applies when**: The customer asks where the order is.

**Agent must not**: Name a carrier or a tracking number that is not on the order record.

**Example**: Status is shipped, ship date is filled in, delivery date is empty. The draft says it has shipped and the delivery date is not on the order. It cites ORD-TRACK.

## ORD-PARTIAL-CANCEL

**Rule**: One line can be cancelled while the order status is placed. Other lines stay on the order. The cancelled line is refunded in full, including tax on that line. Outbound shipping is refunded only when the cancelled line was the last remaining line. A partial cancel waits for a person before it is recorded.

**Applies when**: The customer wants to drop one line and keep the rest, and the order is still placed.

**Agent must not**: Cancel one line after the order is packed, or refund shipping while other lines remain.

**Example**: Two lines, status placed, the customer drops the mug. The mug and its tax are refunded. Shipping stays because the coat remains. The draft cites ORD-PARTIAL-CANCEL.
