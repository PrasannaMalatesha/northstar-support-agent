# Payments and pricing

How Northstar charges, taxes, and corrects a price. Card networks are named here. Timing numbers live only in this file.

## PAY-METHODS

**Rule**: Northstar accepts Visa, Mastercard, American Express, Discover, PayPal, Apple Pay, Google Pay, and Northstar gift cards. Northstar does not accept cash on delivery or checks.

**Applies when**: A customer asks how they can pay.

**Agent must not**: Invent a payment method, or say a check or cash on delivery is accepted.

**Example**: A customer asks to pay by check. The draft lists the accepted methods and says checks are not accepted, citing PAY-METHODS.

## PAY-CHARGE-TIMING

**Rule**: The card is authorized when the order is placed and charged when the order ships. A cancelled order that never shipped releases the authorization. It is not a captured charge.

**Applies when**: A customer sees a pending charge before the ship date, or asks when they are charged.

**Agent must not**: Call an authorization a completed charge, or promise the capture time beyond the ship event.

**Example**: Status is placed and the customer sees a pending card amount. The draft says that is an authorization and the charge happens at shipment, citing PAY-CHARGE-TIMING.

## PAY-TAX

**Rule**: Sales tax follows the ship-to address on the order. Support does not recalculate tax from a conversation. The tax amount is the tax stored on the order.

**Applies when**: A customer asks why tax was charged or whether a different address would change it.

**Agent must not**: Quote a tax rate from memory, or change tax without a new ship-to address recorded on the order.

**Example**: The customer asks for the tax to be removed. The draft says tax follows the ship-to address and the amount is the amount on the order, citing PAY-TAX.

## PAY-PRICE-ADJUST

**Rule**: If the same item's price on the Northstar site drops within 14 days of the delivery date, Northstar refunds the difference once for that line. Clearance, final sale, and flash deals are excluded. The difference is the price paid minus the new site price, and it cannot exceed the amount paid for the line.

**Applies when**: The customer asks for a price match after delivery, and the drop is on the Northstar site.

**Agent must not**: Match another store's price, apply the difference twice, or apply it to clearance, final sale, or a flash deal.

**Example**: A kettle delivered 10 days ago is now lower on the Northstar site and was not a flash deal. The proposal is the difference, once, citing PAY-PRICE-ADJUST.

## PAY-PRICE-ERROR

**Rule**: Northstar may cancel an order that contains a pricing error while the status is still placed, and refund the customer in full. Northstar does not cancel a shipped order for a pricing error. The customer is told the price was an error.

**Applies when**: The order record or the handbook identifies the line as a pricing error, and the order is not yet shipped.

**Agent must not**: Declare a pricing error from a customer's guess, or cancel a shipped order for price.

**Example**: Status is placed and the order is flagged as a pricing error. The proposal is a cancel and a full refund, citing PAY-PRICE-ERROR.

## PAY-DUPLICATE

**Rule**: A second pending authorization for the same order drops off in 3 to 5 business days and is not a second charge. A charge that the order record shows as captured twice is escalated under ESC-WHEN. Support does not promise a bank will remove a captured charge on a given day.

**Applies when**: The customer sees two card lines for one order.

**Agent must not**: Treat a pending hold as a captured double charge, or invent a bank posting date.

**Example**: One captured charge and one pending hold. The draft says the hold drops off in 3 to 5 business days, citing PAY-DUPLICATE. Two captured charges escalate.
