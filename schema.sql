CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candle_time TIMESTAMP WITH TIME ZONE NOT NULL,
    lower_bound FLOAT NOT NULL,
    upper_bound FLOAT NOT NULL,
    actual_close FLOAT,
    is_hit BOOLEAN,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    is_gap BOOLEAN DEFAULT false,
    UNIQUE (candle_time)
);
