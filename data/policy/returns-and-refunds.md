# Returns and refunds

Northstar Goods accepts returns of most unused items. These rules are the only return rules.

## REF-WINDOW

A return must be requested within 30 days of the delivery date on the order. The delivery date is the date on the order record, not the date the customer says they opened the box. Requests on day 31 or later are outside the window.

## REF-ELIGIBILITY

An item is eligible for a full refund when all of the following are true: the request is inside REF-WINDOW, the item is unused and in its original packaging, and the line has not already been refunded. The refund amount is the amount paid for that line, including tax charged on that line. Outbound shipping is not refunded unless REF-DAMAGED applies.

## REF-PARTIAL

If the item was used, washed, or is missing packaging, but is still inside REF-WINDOW and has not already been refunded, offer store credit of 50 percent of the line amount. Do not offer a card refund for a used item. The credit amount is half the line total, rounded down to the nearest cent.

## REF-DENY

Deny the refund when any of these are true: the request is outside REF-WINDOW, the line was already refunded, the item is listed under REF-FINAL-SALE, or the order id does not match the customer on the order record. Say which rule applies. Do not offer a goodwill exception.

## REF-DAMAGED

If the customer reports that the item arrived damaged or not as described, and the request is within 14 days of the delivery date, approve a full refund of the line including outbound shipping charged on the order. The item does not need to be unused. This 14-day damage rule does not extend the 30-day window in REF-WINDOW for ordinary change-of-mind returns.

## REF-FINAL-SALE

Gift cards, items marked Final Sale on the order line, and underwear or earrings with broken hygiene seals are not returnable. Deny those lines even inside REF-WINDOW.
