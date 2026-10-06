# Shipping and delivery

Shipping times and prices live here. A lost-package count is not the damage-report count in REF-DAMAGED.

## SHIP-REGIONS

**Rule**: Northstar ships to all 50 US states. Northstar does not ship internationally, to US territories, or to military mail addresses.

**Applies when**: A customer asks where Northstar ships.

**Agent must not**: Quote a rate or a delivery promise for an address outside the 50 states.

**Example**: A customer in Hawaii can be shipped. A customer in London cannot. The draft cites SHIP-REGIONS.

## SHIP-OPTIONS

**Rule**: Standard shipping is free when the merchandise total before tax is over $50. Otherwise standard shipping is $5.95. Express shipping is $14.95. The amount charged is the amount on the order.

**Applies when**: A customer asks what shipping costs, before or after an order exists.

**Agent must not**: Promise free shipping on an order whose merchandise total is not over the threshold, or invent a third speed.

**Example**: A $42 kettle pays $5.95 for standard, or $14.95 for express. A $60 kettle pays nothing for standard. The draft cites SHIP-OPTIONS.

## SHIP-SLA

**Rule**: Northstar takes 1 business day to move an order from placed to shipped. After the ship date on the order, standard delivery is 5 to 7 business days, and express delivery is 2 business days. Alaska and Hawaii add 3 business days to that delivery span. Business days are Monday through Friday. Northstar does not promise a delivery date that is not on the order record.

**Applies when**: A customer asks how long shipping takes, and the order's ship date or status is known.

**Agent must not**: Invent a carrier name, a tracking number, or a calendar date that the order record does not store.

**Example**: An order marked shipped on Monday with standard shipping is described as 5 to 7 business days from that Monday. The draft cites SHIP-SLA and does not name a carrier.

## SHIP-DELAY

**Rule**: A shipment is delayed when the order is marked shipped and the delivery date is still empty more than 2 business days after the SHIP-SLA window. The specialist tells the customer the order is delayed and asks them to wait 2 more business days. Do not refund a delayed shipment during that extra wait unless the customer also has a REF-DAMAGED claim.

**Applies when**: The order is shipped, has no delivery date, and the SLA window plus the extra days has started.

**Agent must not**: Refund only because a package is late inside that extra wait, or call it lost.

**Example**: Standard shipping's window has ended and two further business days have not. The draft says the order is delayed and asks the customer to wait, citing SHIP-DELAY.

## SHIP-LOST

**Rule**: A shipment is lost when the order is marked shipped and the delivery date is still empty 14 days after the ship date. Then the customer may take a full refund of the unreceived lines, including outbound shipping, without returning an item. Do not call a package lost before that day. This count starts on the ship date. It is not the damage-report count in REF-DAMAGED, which starts on the delivery date.

**Applies when**: A shipped order still has an empty delivery date and the customer says it never arrived.

**Agent must not**: Call a package lost before day 14 from the ship date, or ask the customer to return an item they did not receive.

**Example**: Shipped on 1 April, still no delivery date on 16 April. The proposal may refund the unreceived lines and outbound shipping, citing SHIP-LOST.

## SHIP-ADDRESS

**Rule**: The ship-to address can be changed only when the order status is placed or packed, and the request is made for the customer on the order. Once the status is shipped or delivered, the address cannot be changed. Northstar does not reroute a package that has left the building. Recording the change waits for a person.

**Applies when**: The customer asks to send the order somewhere else.

**Agent must not**: Change an address after the status is shipped, or record the change before a person approves it.

**Example**: Status is placed. The specialist proposes the new address and waits. Status is shipped. The draft says the address cannot be changed, citing SHIP-ADDRESS.

## SHIP-SPLIT

**Rule**: An order may arrive as more than one package. Each package follows SHIP-SLA from its own ship date. A line is missing only when its package is delivered and that line is not in it, which then follows REF-MISSING-ITEM.

**Applies when**: The customer received one box and asks where the rest is, and the order shows more than one shipment.

**Agent must not**: Treat an unshipped second package as a lost or missing line.

**Example**: One line shipped on Monday and the other is still placed. The draft explains the split and cites SHIP-SPLIT. It does not refund the unshipped line.

## SHIP-DNR

**Rule**: When the order says delivered and the customer says they do not have it, ask the customer to wait 48 hours and to check the delivery location. If it is still missing after that wait, escalate under ESC-WHEN. Do not refund during the 48 hours.

**Applies when**: The delivery date is filled in and the customer reports they did not receive the package.

**Agent must not**: Refund in the first 48 hours, or invent a carrier scan.

**Example**: Delivered this morning. The draft asks the customer to wait 48 hours and check the doorway, citing SHIP-DNR.

## SHIP-REFUSED

**Rule**: A package the customer refuses is a return. Outbound shipping charged on the order is not refunded. The return window does not apply, because the customer did not keep the item. Condition rules do not apply. Final-sale lines are still not refunded as merchandise, and their outbound shipping is not refunded either.

**Applies when**: The order shows the package was refused.

**Agent must not**: Refund the outbound shipping on a refusal, or treat a refusal as damage.

**Example**: The customer refused the box at the door. Merchandise can be refunded. The shipping charge stays. The draft cites SHIP-REFUSED.
