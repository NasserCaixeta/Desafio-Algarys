SELECT 'CREATE DATABASE clinic_confirmations_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'clinic_confirmations_test')\gexec
