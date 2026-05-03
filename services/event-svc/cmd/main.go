package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	newrelic "github.com/newrelic/go-agent/v3/newrelic"
	nrgin "github.com/newrelic/go-agent/v3/integrations/nrgin"
	_ "github.com/newrelic/go-agent/v3/integrations/nrpq"
	"go.uber.org/zap"
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
var nrApp *newrelic.Application
var logger *zap.Logger
var bugStaleCache = os.Getenv("BUG_STALE_CACHE") == "true"

func main() {
	var err error
	logger, err = zap.NewProduction()
	if err != nil {
		panic("failed to init logger: " + err.Error())
	}
	defer logger.Sync()

	logger.Info("event-svc starting",
		zap.String("version", "pulse"),
		zap.Bool("bug_stale_cache", bugStaleCache),
	)

	// New Relic
	app, nrErr := newrelic.NewApplication(
		newrelic.ConfigAppName(getEnv("NEW_RELIC_APP_NAME", "pulse-event-svc")),
		newrelic.ConfigLicense(getEnv("NEW_RELIC_LICENSE_KEY", "")),
		newrelic.ConfigDistributedTracerEnabled(true),
		newrelic.ConfigAppLogForwardingEnabled(true),
	)
	if nrErr != nil {
		logger.Warn("New Relic not configured — APM disabled", zap.Error(nrErr))
	} else {
		logger.Info("New Relic agent initialized")
	}
	nrApp = app

	// Database
	dsn := "host=" + getEnv("POSTGRES_HOST", "localhost") +
		" port=" + getEnv("POSTGRES_PORT", "5432") +
		" user=" + getEnv("POSTGRES_USER", "pulse") +
		" password=" + getEnv("POSTGRES_PASSWORD", "") +
		" dbname=" + getEnv("POSTGRES_DB", "pulse") +
		" sslmode=disable"

	db, err = sql.Open("nrpostgres", dsn)
	if err != nil {
		logger.Fatal("failed to open DB", zap.Error(err))
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		logger.Fatal("DB ping failed", zap.Error(err))
	}
	logger.Info("connected to PostgreSQL",
		zap.String("host", getEnv("POSTGRES_HOST", "localhost")),
		zap.String("db", getEnv("POSTGRES_DB", "pulse")),
	)

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
	r.PUT("/user/preferences", updatePreferencesHandler)
	r.GET("/user/saved-events", getSavedEventsHandler)
	r.POST("/user/saved-events", saveEventHandler)
	r.DELETE("/user/saved-events/:event_id", unsaveEventHandler)

	port := getEnv("PORT", "8080")
	logger.Info("event-svc ready", zap.String("port", port))
	r.Run(":" + port)
}

func healthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "event-svc"})
}

func getEventsHandler(c *gin.Context) {
	city := c.DefaultQuery("city", getEnv("DEMO_CITY", "London"))
	logger.Debug("fetching events", zap.String("city", city))

	rows, err := db.QueryContext(c.Request.Context(),
		`SELECT id, title, description, category, venue, address, city, date, price_gbp, tags
		 FROM events WHERE city = $1 ORDER BY date ASC`, city)
	if err != nil {
		logger.Error("DB query failed in getEvents", zap.String("city", city), zap.Error(err))
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
			logger.Warn("event row scan error", zap.Error(err))
			continue
		}
		events = append(events, e)
	}

	logger.Info("events fetched", zap.String("city", city), zap.Int("count", len(events)))

	if bugStaleCache {
		logger.Warn("BUG_STALE_CACHE active — shifting event dates -45 days",
			zap.String("bug", "BUG_STALE_CACHE"),
			zap.Int("count", len(events)),
		)
		for i := range events {
			events[i].Date = events[i].Date.Add(-45 * 24 * time.Hour)
		}
		if nrApp != nil {
			nrApp.RecordCustomEvent("BugScenarioEnabled", map[string]interface{}{
				"bug":          "BUG_STALE_CACHE",
				"service":      "event-svc",
				"events_count": len(events),
			})
		}
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
		logger.Warn("event not found", zap.String("event_id", id))
		c.JSON(http.StatusNotFound, gin.H{"error": "event not found"})
		return
	}
	if err != nil {
		logger.Error("DB query failed in getEvent", zap.String("event_id", id), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	logger.Info("event fetched", zap.String("event_id", id), zap.String("title", e.Title))
	c.JSON(http.StatusOK, e)
}

func getEventsByCategoryHandler(c *gin.Context) {
	category := c.Param("category")
	rows, err := db.QueryContext(c.Request.Context(),
		`SELECT id, title, description, category, venue, address, city, date, price_gbp, tags
		 FROM events WHERE category = $1 ORDER BY date ASC`, category)
	if err != nil {
		logger.Error("DB query failed in getEventsByCategory", zap.String("category", category), zap.Error(err))
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
			logger.Warn("category event row scan error", zap.String("category", category), zap.Error(err))
			continue
		}
		events = append(events, e)
	}
	logger.Info("events by category fetched", zap.String("category", category), zap.Int("count", len(events)))
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
		logger.Warn("user not found", zap.String("user_id", userID))
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}
	if err != nil {
		logger.Error("DB query failed in getUser", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	logger.Info("user fetched", zap.String("user_id", u.ID), zap.Bool("ai_enabled", u.AIEnabled))
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
		logger.Warn("invalid AI preference payload", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	_, err := db.ExecContext(c.Request.Context(),
		`UPDATE users SET ai_enabled = $1, ai_opt_out_reason = $2, updated_at = NOW()
		 WHERE id = $3`, req.AIEnabled, req.Reason, userID)
	if err != nil {
		logger.Error("DB update failed in updateAIPreference", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if req.AIEnabled {
		logger.Info("user enabled AI", zap.String("user_id", userID))
	} else {
		reason := ""
		if req.Reason != nil {
			reason = *req.Reason
		}
		logger.Info("user disabled AI", zap.String("user_id", userID), zap.String("reason", reason))
		db.ExecContext(context.Background(),
			`INSERT INTO ai_opt_out_log (user_id, reason) VALUES ($1, $2)`,
			userID, req.Reason)
	}

	c.JSON(http.StatusOK, gin.H{"ai_enabled": req.AIEnabled})
}

type UpdatePreferencesRequest struct {
	Categories []string `json:"categories"`
}

func updatePreferencesHandler(c *gin.Context) {
	userID := getEnv("DEMO_USER_ID", "demo_user")
	var req UpdatePreferencesRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		logger.Warn("invalid preferences payload", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	prefsJSON, _ := json.Marshal(map[string]interface{}{
		"categories": req.Categories,
		"times":      []string{"evening", "weekend"},
		"radius_km":  10,
	})
	_, err := db.ExecContext(c.Request.Context(),
		`UPDATE users SET preferences = $1, updated_at = NOW() WHERE id = $2`,
		string(prefsJSON), userID)
	if err != nil {
		logger.Error("DB update failed in updatePreferences", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	logger.Info("user preferences updated", zap.String("user_id", userID), zap.Strings("categories", req.Categories))
	c.JSON(http.StatusOK, gin.H{"categories": req.Categories})
}

type SaveEventRequest struct {
	EventID string `json:"event_id" binding:"required"`
}

func getSavedEventsHandler(c *gin.Context) {
	userID := getEnv("DEMO_USER_ID", "demo_user")
	rows, err := db.QueryContext(c.Request.Context(),
		`SELECT event_id FROM saved_events WHERE user_id = $1 ORDER BY saved_at DESC`, userID)
	if err != nil {
		logger.Error("DB query failed in getSavedEvents", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer rows.Close()
	ids := []string{}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err == nil {
			ids = append(ids, id)
		}
	}
	logger.Debug("saved events fetched", zap.String("user_id", userID), zap.Int("count", len(ids)))
	c.JSON(http.StatusOK, gin.H{"saved_event_ids": ids})
}

func saveEventHandler(c *gin.Context) {
	userID := getEnv("DEMO_USER_ID", "demo_user")
	var req SaveEventRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		logger.Warn("invalid save event payload", zap.String("user_id", userID), zap.Error(err))
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	_, err := db.ExecContext(c.Request.Context(),
		`INSERT INTO saved_events (user_id, event_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
		userID, req.EventID)
	if err != nil {
		logger.Error("DB insert failed in saveEvent", zap.String("user_id", userID), zap.String("event_id", req.EventID), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	logger.Info("event saved", zap.String("user_id", userID), zap.String("event_id", req.EventID))
	c.JSON(http.StatusCreated, gin.H{"saved": true, "event_id": req.EventID})
}

func unsaveEventHandler(c *gin.Context) {
	userID := getEnv("DEMO_USER_ID", "demo_user")
	eventID := c.Param("event_id")
	_, err := db.ExecContext(c.Request.Context(),
		`DELETE FROM saved_events WHERE user_id = $1 AND event_id = $2`, userID, eventID)
	if err != nil {
		logger.Error("DB delete failed in unsaveEvent", zap.String("user_id", userID), zap.String("event_id", eventID), zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	logger.Info("event unsaved", zap.String("user_id", userID), zap.String("event_id", eventID))
	c.JSON(http.StatusOK, gin.H{"saved": false, "event_id": eventID})
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
