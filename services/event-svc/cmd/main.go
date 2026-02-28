package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	_ "github.com/lib/pq"
	newrelic "github.com/newrelic/go-agent/v3/newrelic"
	nrgin "github.com/newrelic/go-agent/v3/integrations/nrgin"
)

type Event struct {
	ID          string    `json:"id"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	Category    string    `json:"category"`
	Venue       string    `json:"venue"`
	Address     string    `json:"address"`
	City        string    `json:"city"`
	Date        time.Time `json:"date"`
	PriceGBP    *float64  `json:"price_gbp"`
	Tags        []string  `json:"tags"`
}

type User struct {
	ID              string          `json:"id"`
	DisplayName     string          `json:"display_name"`
	Location        string          `json:"location"`
	AIEnabled       bool            `json:"ai_enabled"`
	AIOptOutReason  *string         `json:"ai_opt_out_reason"`
	Preferences     json.RawMessage `json:"preferences"`
}

var db *sql.DB

func main() {
	// New Relic
	app, err := newrelic.NewApplication(
		newrelic.ConfigAppName(getEnv("NEW_RELIC_APP_NAME", "pulse-event-svc")),
		newrelic.ConfigLicense(getEnv("NEW_RELIC_LICENSE_KEY", "")),
		newrelic.ConfigDistributedTracerEnabled(true),
		newrelic.ConfigAppLogForwardingEnabled(true),
	)
	if err != nil {
		log.Printf("WARN: New Relic not configured: %v", err)
	}

	// Database
	dsn := "host=" + getEnv("POSTGRES_HOST", "localhost") +
		" port=" + getEnv("POSTGRES_PORT", "5432") +
		" user=" + getEnv("POSTGRES_USER", "pulse") +
		" password=" + getEnv("POSTGRES_PASSWORD", "") +
		" dbname=" + getEnv("POSTGRES_DB", "pulse") +
		" sslmode=disable"

	db, err = sql.Open("postgres", dsn)
	if err != nil {
		log.Fatalf("DB connect error: %v", err)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		log.Fatalf("DB ping error: %v", err)
	}
	log.Println("Connected to PostgreSQL")

	// Router
	r := gin.New()
	r.Use(gin.Logger(), gin.Recovery())
	if app != nil {
		r.Use(nrgin.Middleware(app))
	}

	// CORS
	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type,Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	r.GET("/health", healthHandler)
	r.GET("/events", getEventsHandler)
	r.GET("/events/:id", getEventHandler)
	r.GET("/events/category/:category", getEventsByCategoryHandler)
	r.GET("/user", getUserHandler)
	r.PUT("/user/ai-preference", updateAIPreferenceHandler)

	port := getEnv("PORT", "8080")
	log.Printf("event-svc listening on :%s", port)
	r.Run(":" + port)
}

func healthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "event-svc"})
}

func getEventsHandler(c *gin.Context) {
	txn := newrelic.FromContext(c.Request.Context())
	defer txn.StartSegment("db.query.events").End()

	rows, err := db.QueryContext(c.Request.Context(),
		`SELECT id, title, description, category, venue, address, city, date, price_gbp, tags
		 FROM events ORDER BY date ASC`)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer rows.Close()

	events := []Event{}
	for rows.Next() {
		var e Event
		if err := rows.Scan(&e.ID, &e.Title, &e.Description, &e.Category,
			&e.Venue, &e.Address, &e.City, &e.Date, &e.PriceGBP,
			pqArray(&e.Tags)); err != nil {
			log.Printf("scan error: %v", err)
			continue
		}
		events = append(events, e)
	}
	c.JSON(http.StatusOK, events)
}

func getEventHandler(c *gin.Context) {
	id := c.Param("id")
	var e Event
	err := db.QueryRowContext(c.Request.Context(),
		`SELECT id, title, description, category, venue, address, city, date, price_gbp, tags
		 FROM events WHERE id = $1`, id).
		Scan(&e.ID, &e.Title, &e.Description, &e.Category,
			&e.Venue, &e.Address, &e.City, &e.Date, &e.PriceGBP,
			pqArray(&e.Tags))
	if err == sql.ErrNoRows {
		c.JSON(http.StatusNotFound, gin.H{"error": "event not found"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, e)
}

func getEventsByCategoryHandler(c *gin.Context) {
	category := c.Param("category")
	rows, err := db.QueryContext(c.Request.Context(),
		`SELECT id, title, description, category, venue, address, city, date, price_gbp, tags
		 FROM events WHERE category = $1 ORDER BY date ASC`, category)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer rows.Close()

	events := []Event{}
	for rows.Next() {
		var e Event
		if err := rows.Scan(&e.ID, &e.Title, &e.Description, &e.Category,
			&e.Venue, &e.Address, &e.City, &e.Date, &e.PriceGBP,
			pqArray(&e.Tags)); err != nil {
			continue
		}
		events = append(events, e)
	}
	c.JSON(http.StatusOK, events)
}

func getUserHandler(c *gin.Context) {
	userID := getEnv("DEMO_USER_ID", "demo_user")
	var u User
	err := db.QueryRowContext(c.Request.Context(),
		`SELECT id, display_name, location, ai_enabled, ai_opt_out_reason, preferences
		 FROM users WHERE id = $1`, userID).
		Scan(&u.ID, &u.DisplayName, &u.Location, &u.AIEnabled,
			&u.AIOptOutReason, &u.Preferences)
	if err == sql.ErrNoRows {
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, u)
}

type AIPreferenceRequest struct {
	AIEnabled bool    `json:"ai_enabled"`
	Reason    *string `json:"reason"`
}

func updateAIPreferenceHandler(c *gin.Context) {
	userID := getEnv("DEMO_USER_ID", "demo_user")
	var req AIPreferenceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	_, err := db.ExecContext(c.Request.Context(),
		`UPDATE users SET ai_enabled = $1, ai_opt_out_reason = $2, updated_at = NOW()
		 WHERE id = $3`, req.AIEnabled, req.Reason, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Log opt-out for NR observability
	if !req.AIEnabled {
		db.ExecContext(context.Background(),
			`INSERT INTO ai_opt_out_log (user_id, reason) VALUES ($1, $2)`,
			userID, req.Reason)
	}

	c.JSON(http.StatusOK, gin.H{"ai_enabled": req.AIEnabled})
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// pqArray wraps string slice for postgres driver
func pqArray(a *[]string) interface{} {
	return (*stringArray)(a)
}

type stringArray []string

func (a *stringArray) Scan(src interface{}) error {
	// Simple implementation for demo
	*a = []string{}
	return nil
}
