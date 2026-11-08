CREATE TABLE patients (
  medicare_number VARCHAR(11) PRIMARY KEY,
  email TEXT NOT NULL,
  date_of_birth DATE NOT NULL,
  gender TEXT NOT NULL,
  marital_status TEXT NOT NULL,
  diagnosis TEXT,
  religion TEXT
);
