# Returns and refunds

These rules are the only return rules. The window length for each category is in REF-CATEGORY. Other sections name that id instead of repeating the length.

## REF-WINDOW

**Rule**: A return window starts on the delivery date stored on the order. The length of the window is the length in REF-CATEGORY for that line's category. A request on the day after the window ends is outside the window. The delivery date is the date on the order record.

**Applies when**: A customer wants to return an item, or asks how long they have.

**Agent must not**: Start the window from the day the customer says they opened the box, or from the order date.

**Example**: An apparel line shows delivered on 1 March. The specialist uses the apparel length in REF-CATEGORY, counted from 1 March. The draft cites REF-WINDOW and REF-CATEGORY.

## REF-CATEGORY

**Rule**: Apparel and footwear, bags and accessories, and home and kitchen may be returned for the 30 days in REF-WINDOW. Small electronics may be returned for the 15 days in REF-WINDOW. The category is the category on the catalog row for that line.

**Applies when**: The specialist needs the length of a return or needs to tell two categories apart.

**Agent must not**: Use one length for every category, or use a length that is not written here.

**Example**: A speaker is small electronics and a wool coat is apparel. The coat uses the longer window. The speaker uses the shorter window. The draft cites REF-CATEGORY.

## REF-CONDITION

**Rule**: Apparel and footwear must be unworn, unwashed, and have the original tags on. Small electronics must include every accessory that shipped with the line, in the original packaging. Bags and accessories, and home and kitchen, must be unused and in the original packaging.

**Applies when**: A return asks for a full refund and the item's condition is known.

**Agent must not**: Treat a worn item as eligible for a full card refund. Used items follow REF-PARTIAL.

**Example**: A coat comes back with the tags removed. It fails REF-CONDITION. If it is still inside the window and was not already refunded, the proposal is store credit under REF-PARTIAL, not a card refund.

## REF-ELIGIBILITY

**Rule**: An item is eligible for a full refund when all of the following are true: the request is inside REF-WINDOW for that category, the item meets REF-CONDITION, the line is not final sale under REF-FINAL-SALE, and the line has not already been refunded. The refund amount is the amount paid for that line, including tax charged on that line. Outbound shipping is not refunded unless REF-DAMAGED applies.

**Applies when**: The specialist is deciding a full refund on a returned line.

**Agent must not**: Add outbound shipping to an ordinary return, or refund a line that already shows a refund.

**Example**: A unused kettle, inside the home-and-kitchen window, with packaging, and no prior refund, is a full refund of the line and its tax. The draft cites REF-ELIGIBILITY.

## REF-PARTIAL

**Rule**: If the item was used, washed, or is missing packaging, but is still inside REF-WINDOW and has not already been refunded, offer store credit of 50 percent of the line amount. Do not offer a card refund for a used item. The credit amount is half the line total, rounded down to the nearest cent.

**Applies when**: The item is inside the window but fails REF-CONDITION, and it is not final sale.

**Agent must not**: Offer a card refund for a used item, or round the credit up.

**Example**: A line paid at $40.00 comes back washed. Store credit is $20.00. The draft cites REF-PARTIAL.

## REF-DENY

**Rule**: Deny the refund when any of these are true: the request is outside REF-WINDOW, the line was already refunded, the item is listed under REF-FINAL-SALE, or the order does not belong to the case customer. Say which rule applies. Do not offer a goodwill exception.

**Applies when**: One of those deny reasons is present.

**Agent must not**: Invent an exception, a courtesy credit, or a manager override.

**Example**: The delivery date is past the electronics window and the item is not damaged. The proposal is deny, citing REF-DENY and REF-CATEGORY.

## REF-DAMAGED

**Rule**: If the customer reports that the item arrived damaged or not as described, and the report is within 14 days of the delivery date, approve a full refund of the line, including outbound shipping charged on the order. The item does not need to meet REF-CONDITION. This damage report window is shorter than the electronics return window in REF-CATEGORY on purpose. It does not extend REF-WINDOW for a change of mind.

**Applies when**: The customer reports damage or a wrong description, and the delivery date is known.

**Agent must not**: Use this 14-day count for a change of mind, for a lost package, or for a price drop.

**Example**: A lamp arrives cracked on day 10. The proposal is a full refund of the line plus the outbound shipping on the order, citing REF-DAMAGED.

## REF-WRONG-ITEM

**Rule**: If the item in hand is a different item from the line on the order, the customer may return it for a full refund of that line, including outbound shipping charged on the order. The report uses the damage report window in REF-DAMAGED. Northstar pays return shipping under REF-SHIP-COST.

**Applies when**: The customer received a different item than the line they paid for.

**Agent must not**: Treat a wrong item as a change of mind, or ask the customer to pay the label fee.

**Example**: The order line is a blue mug and the box contains a plate. The proposal is a full refund of the mug line, citing REF-WRONG-ITEM.

## REF-MISSING-ITEM

**Rule**: If a line was paid and the shipment arrives without that line, refund the missing line in full, including tax on that line and the outbound shipping charged for the order if no other line remains. The customer does not return an item they did not receive. The report uses the damage report window in REF-DAMAGED.

**Applies when**: A paid line is absent from the delivered shipment.

**Agent must not**: Ask for a return of an item the customer does not have, or mark the line delivered as received.

**Example**: Two lines were paid and only one is in the box. The missing line is refunded in full, citing REF-MISSING-ITEM.

## REF-FINAL-SALE

**Rule**: Gift cards, lines marked final sale on the order, underwear, earrings whose hygiene seal is broken, and opened in-ear earbuds are not returnable. Deny those lines even inside REF-WINDOW. Opened in-ear earbuds that are defective follow REF-DAMAGED or the warranty, not this deny.

**Applies when**: The line is one of those kinds, or the order line is marked final sale.

**Agent must not**: Offer a change-of-mind return on a final-sale line.

**Example**: Opened in-ear earbuds with no defect are denied, citing REF-FINAL-SALE. The same earbuds reported dead on arrival inside the damage window follow REF-DAMAGED.

## REF-METHOD

**Rule**: A full refund goes back to the original payment method. The customer may choose store credit instead. A partial credit under REF-PARTIAL is store credit only.

**Applies when**: A return has been approved and the form of the money is being stated.

**Agent must not**: Send a card refund for a used item, or send cash.

**Example**: An eligible unused coat is refunded to the card used at purchase, unless the customer asks for store credit. The draft cites REF-METHOD.

## REF-TIMING

**Rule**: After Northstar receives the return, Northstar finishes its side within 3 business days. A refund to a credit card then takes 3 to 5 business days. A refund to a debit card takes up to 10 business days. Store credit appears within 24 hours of Northstar finishing its side. Business days are Monday through Friday.

**Applies when**: A customer asks when the money will show up.

**Agent must not**: Promise a card refund on the day the return is scanned, or quote a speed that is not in this section.

**Example**: Northstar receives a coat on Monday and finishes on Wednesday. Store credit, if chosen, is there by Thursday. A credit-card refund still has the card's own days after Wednesday. The draft cites REF-TIMING.

## REF-SHIP-COST

**Rule**: When Northstar is at fault, including damage, a wrong item, or a missing item, the return label is free. Otherwise a label fee of $6.00 is taken out of the refund. A return taken as store credit has no label fee.

**Applies when**: A return needs a label, or the specialist is explaining what the customer will pay to send the item back.

**Agent must not**: Charge the label fee on a Northstar-fault return, or charge it on a store-credit return.

**Example**: A change-of-mind return of an unused kettle uses the label fee, taken out of the refund. A cracked lamp does not. The draft cites REF-SHIP-COST.

## REF-GIFT

**Rule**: A return of a gift is paid to the recipient as store credit. It is not refunded to the purchaser's card. The recipient needs the order id. The window and condition rules still apply.

**Applies when**: The person asking for the return is the recipient of a gift, not the purchaser.

**Agent must not**: Put the gift refund back on the purchaser's card, or skip the window because the item was a gift.

**Example**: A gift coat is inside the window and unworn. The recipient receives store credit. The draft cites REF-GIFT and REF-ELIGIBILITY.

## REF-HOLIDAY

**Rule**: A line bought from 1 November through 24 December may be returned until 31 January, even when REF-CATEGORY would end sooner. Final-sale lines stay final sale. The damage report window in REF-DAMAGED does not change.

**Applies when**: The purchase date on the order falls in that buying span, and the customer asks for a change-of-mind return.

**Agent must not**: Apply this later end date to a purchase outside that span, or to a damage report.

**Example**: A coat bought on 20 December may be returned through 31 January. A coat bought on 20 October uses REF-CATEGORY only. The draft cites REF-HOLIDAY.

## REF-INSPECTION

**Rule**: When a returned item does not match the condition the customer stated, Northstar refuses the full refund and instead follows the rule that matches the item in hand. A used item becomes REF-PARTIAL. A final-sale item becomes REF-DENY. Northstar tells the customer which rule changed the outcome.

**Applies when**: The warehouse has received the item and it does not match the claim.

**Agent must not**: Keep a full-refund proposal after inspection shows the condition failed.

**Example**: The customer said the coat was unworn. Inspection finds it washed. The outcome changes to store credit under REF-PARTIAL. The draft cites REF-INSPECTION.
