"""Post-entry lifecycle (TRD-REV51-099, 106, 107, 108, 110, 111).

Everything here runs after a position exists. None of it sizes, sends or
approves: the Risk Authority remains the only live numeric sizer and the
Execution Router the only order-sending boundary. What these modules do is
decide when a position must be protected, when a family has released enough
risk to be considered for more, and — behind an explicit shadow gate — when
an expansion would have been worth proposing.
"""
